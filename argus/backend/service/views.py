import datetime
import logging
from functools import partial, reduce
from typing import TypedDict
from uuid import UUID

from cassandra.cqlengine.models import Model
from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.pytest import PytestResultTable
from argus.backend.models.web import (
    ArgusGroup, ArgusRelease, ArgusTest, ArgusUserView, ReleaseDistinctImages,
    ReleaseDistinctVersions, User,
)
from argus.backend.plugins.loader import AVAILABLE_PLUGINS, all_plugin_models
from argus.backend.service.stats_snapshot import invalidate_view
from argus.backend.service.test_lookup import TestLookup
from argus.backend.util.common import chunk, current_user

LOGGER = logging.getLogger(__name__)


class UserViewException(Exception):
    pass


class ViewUpdateRequest(TypedDict):
    name: str
    description: str
    display_name: str
    tests: list[str]
    widget_settings: str
    plan_id: str | None


class UserViewService:
    def create_view(self, name: str, items: list[str], widget_settings: str, description: str = None, display_name: str = None, plan_id: UUID = None) -> ArgusUserView:
        try:
            name_check = ArgusUserView.get(name=name)
            raise UserViewException(
                f"View with name {name} already exists: {name_check.id}", name, name_check, name_check.id)
        except ArgusUserView.DoesNotExist:
            pass
        view = ArgusUserView()
        view.name = name
        view.display_name = display_name or name
        view.description = description
        view.widget_settings = widget_settings
        view.plan_id = plan_id
        view.tests = []
        entities = self.parse_view_entity_list(items)
        view.tests = entities["tests"]
        view.release_ids = entities["release"]
        view.group_ids = entities["group"]
        view.user_id = current_user().id

        view.save()
        return view

    def parse_view_entity_list(self, entity_list: list[str]) -> dict[str, list[str]]:
        entities = {
            "release": [],
            "group": [],
            "tests": []
        }
        for entity in entity_list:
            entity_type, entity_id = entity.split(":")
            match (entity_type):
                case "release":
                    entities["tests"].extend(t.id for t in ArgusTest.filter(release_id=entity_id).all())
                    entities["release"].append(entity_id)
                case "group":
                    entities["tests"].extend(t.id for t in ArgusTest.filter(group_id=entity_id).all())
                    entities["group"].append(entity_id)
                case "test":
                    entities["tests"].append(entity_id)
        return entities

    def test_lookup(self, query: str):
        return TestLookup.test_lookup(query)

    def update_view(self, view_id: str | UUID, update_data: ViewUpdateRequest) -> bool:
        view: ArgusUserView = ArgusUserView.get(id=view_id)
        if view.user_id != current_user().id and not current_user().is_admin():
            raise UserViewException("Unable to modify other users' views")
        for key in ["user_id", "id"]:
            update_data.pop(key, None)
        items = update_data.pop("items")
        for k, value in update_data.items():
            view[k] = value
        view.tests = []
        view.release_ids = []
        view.group_ids = []
        for entity in items:
            entity_type, entity_id = entity.split(":")
            match (entity_type):
                case "release":
                    view.tests.extend(t.id for t in ArgusTest.filter(release_id=entity_id).all())
                    view.release_ids.append(entity_id)
                case "group":
                    view.tests.extend(t.id for t in ArgusTest.filter(group_id=entity_id).all())
                    view.group_ids.append(entity_id)
                case "test":
                    view.tests.append(entity_id)
        view.last_updated = datetime.datetime.utcnow()
        view.save()
        # Drop all cached stats snapshots — test set changed
        try:
            invalidate_view(view.id)
        except Exception:
            LOGGER.warning("Failed to invalidate view snapshot on update for view %s", view_id, exc_info=True)
        return True

    def delete_view(self, view_id: str | UUID) -> bool:
        view = ArgusUserView.get(id=view_id)
        if view.user_id != current_user().id and not current_user().is_admin():
            raise UserViewException("Unable to modify other users' views")
        view.delete()

        return True

    def get_view(self, view_id: str | UUID) -> ArgusUserView:
        view: ArgusUserView = ArgusUserView.get(id=view_id)
        if datetime.datetime.utcnow() - (view.last_updated or datetime.datetime.fromtimestamp(0)) > datetime.timedelta(hours=1):
            self.refresh_stale_view(view)
        return view

    def get_view_by_name(self, view_name: str) -> ArgusUserView:
        view: ArgusUserView = ArgusUserView.get(name=view_name)
        if datetime.datetime.utcnow() - (view.last_updated or datetime.datetime.fromtimestamp(0)) > datetime.timedelta(hours=1):
            self.refresh_stale_view(view)
        return view

    def get_all_views(self, user: User | None = None) -> list[ArgusUserView]:
        if user:
            return list(ArgusUserView.filter(user_id=user.id).all())
        return list(ArgusUserView.filter().all())

    def resolve_view_tests(self, view_id: str | UUID) -> list[ArgusTest]:
        view = ArgusUserView.get(id=view_id)
        return self.resolve_tests_by_id(view.tests)

    def resolve_tests_by_id(self, test_ids: list[str | UUID]) -> list[ArgusTest]:
        tests = []
        for batch in chunk(test_ids):
            tests.extend(ArgusTest.filter(id__in=batch).all())

        return tests

    def batch_resolve_entity(self, entity: Model, param_name: str, entity_ids: list[UUID]) -> list[Model]:
        result = []
        for batch in chunk(entity_ids):
            result.extend(entity.filter(**{f"{param_name}__in": batch}).allow_filtering().all())
        return result

    def refresh_stale_view(self, view: ArgusUserView):
        if view.plan_id:
            try:
                view.tests = [test.id for test in self.resolve_tests_by_id(ArgusReleasePlan.get(id=view.plan_id).tests)]
                view.group_ids = ArgusReleasePlan.get(id=view.plan_id).groups
            except ArgusReleasePlan.DoesNotExist:
                LOGGER.warning("Dangling view %s from non-existent release plan %s", view.id, view.plan_id)
                return view
        else:
            view.tests = [test.id for test in self.resolve_view_tests(view.id)]
        all_tests = set(view.tests)
        all_tests.update(test.id for test in self.batch_resolve_entity(ArgusTest, "group_id", view.group_ids))
        all_tests.update(test.id for test in self.batch_resolve_entity(ArgusTest, "release_id", view.release_ids))
        view.tests = list(all_tests)
        view.last_updated = datetime.datetime.utcnow()
        view.save()
        # Drop all cached stats snapshots — test set may have changed
        try:
            invalidate_view(view.id)
        except Exception:
            LOGGER.warning("Failed to invalidate view snapshot on refresh for view %s", view.id, exc_info=True)

        return view

    def resolve_releases_for_tests(self, tests: list[ArgusTest]):
        releases = []
        unique_release_ids = reduce(lambda releases, test: releases.add(test.release_id) or releases, tests, set())
        for batch in chunk(unique_release_ids):
            releases.extend(ArgusRelease.filter(id__in=batch).all())

        return releases

    def resolve_groups_for_tests(self, tests: list[ArgusTest]):
        releases = []
        unique_release_ids = reduce(lambda groups, test: groups.add(test.group_id) or groups, tests, set())
        for batch in chunk(unique_release_ids):
            releases.extend(ArgusGroup.filter(id__in=batch).all())

        return releases

    def get_pytest_view_results(self, view_id: str | UUID) -> list[PytestResultTable]:

        view: ArgusUserView = ArgusUserView.get(id=view_id)
        tests: list[ArgusTest] = []
        for batch in chunk(view.tests):
            tests.extend(ArgusTest.filter(id__in=batch).all())
        tests = [test for test in tests if test.plugin_name == "generic"]
        results = []
        for batch in chunk(tests):
            results.extend(PytestResultTable.filter(test_id__in=[t.id for t in batch]).allow_filtering().all())

        return results

    def _release_ids_for_view(self, view: ArgusUserView) -> set[UUID]:
        """Compute the full set of release ids covered by a view.

        Unions: explicit release_ids + releases derived from group_ids + releases
        from the individual test list (view.tests).
        """
        release_ids: set[UUID] = set(view.release_ids or [])
        for batch in chunk(view.group_ids or []):
            for group in ArgusGroup.filter(id__in=batch).all():
                release_ids.add(group.release_id)
        for batch in chunk(view.tests or []):
            for test in ArgusTest.filter(id__in=batch).all():
                release_ids.add(test.release_id)
        return release_ids

    def get_versions_for_view(self, view_id: str | UUID) -> list[str]:
        """Return distinct scylla_version values for all tests in the view.

        Fast path: union ReleaseDistinctVersions partitions for every release
        covered by the view — O(distinct versions per release), typically <10ms.
        Fallback: if the index is empty for every release (pre-backfill),
        falls back to the old scan path.
        """
        view = ArgusUserView.get(id=view_id)
        release_ids = self._release_ids_for_view(view)

        all_versions: set[str] = set()
        empty_releases: list[UUID] = []

        for release_id in release_ids:
            rows = list(ReleaseDistinctVersions.filter(release_id=release_id).all())
            if rows:
                all_versions.update(r.version for r in rows)
            else:
                empty_releases.append(release_id)

        # Fallback for releases not yet in the index
        if empty_releases:
            tests = self.resolve_view_tests(view_id)
            tests_for_empty = [t for t in tests if t.release_id in set(empty_releases)]
            for plugin in all_plugin_models():
                all_versions.update(plugin.get_distinct_versions_for_view(tests=tests_for_empty))

        return sorted(all_versions, reverse=True)

    def get_images_for_view(self, view_id: str | UUID) -> list[str]:
        """Return distinct cloud image ids for all tests in the view.

        Fast path: union ReleaseDistinctImages partitions for every release
        covered by the view — O(distinct images per release), typically <10ms.
        Fallback: if the index is empty, falls back to the old per-build_id scan.
        """
        view = ArgusUserView.get(id=view_id)
        release_ids = self._release_ids_for_view(view)

        all_images: set[str] = set()
        empty_releases: list[UUID] = []

        for release_id in release_ids:
            rows = list(ReleaseDistinctImages.filter(release_id=release_id).all())
            if rows:
                all_images.update(r.image_id for r in rows)
            else:
                empty_releases.append(release_id)

        # Fallback for releases not yet in the index
        if empty_releases:
            tests = self.resolve_view_tests(view_id)
            tests_for_empty = [t for t in tests if t.release_id in set(empty_releases)]
            fallback_images = AVAILABLE_PLUGINS["scylla-cluster-tests"].model.get_distinct_cloud_images_for_view(
                tests_for_empty
            )
            all_images.update(fallback_images)

        return sorted(all_images, reverse=True)

    def resolve_view_for_edit(self, view_id: str | UUID) -> dict:
        view: ArgusUserView = ArgusUserView.get(id=view_id)
        resolved = dict(view)
        view_groups = self.batch_resolve_entity(ArgusGroup, "id", view.group_ids)
        view_releases = self.batch_resolve_entity(ArgusRelease, "id", view.release_ids)
        view_tests = self.resolve_view_tests(view.id)
        all_groups = {group.id: partial(TestLookup.index_mapper, type="group")(group)
                      for group in self.resolve_releases_for_tests(view_tests)}
        all_releases = {release.id: partial(TestLookup.index_mapper, type="release")(release)
                        for release in self.resolve_releases_for_tests(view_tests)}
        entities_by_id = {
            entity.id: partial(TestLookup.index_mapper, type="release" if isinstance(
                entity, ArgusRelease) else "group")(entity)
            for container in [view_releases, view_groups]
            for entity in container
        }

        items = []
        for test in view_tests:
            if not (entities_by_id.get(test.group_id) or entities_by_id.get(test.release_id)):
                item = dict(test)
                item["type"] = "test"
                items.append(item)

        items = [*entities_by_id.values(), *items]
        for entity in items:
            entity["group"] = all_groups.get(entity.get("group_id"), {}).get(
                "pretty_name") or all_groups.get(entity.get("group_id"), {}).get("name")
            entity["release"] = all_releases.get(entity.get("release_id"), {}).get(
                "pretty_name") or all_releases.get(entity.get("release_id"), {}).get("name")

        resolved["items"] = items
        return resolved
