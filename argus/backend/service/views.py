import asyncio
import datetime
import logging
from functools import partial, reduce
from typing import TypedDict
from uuid import UUID

from coodie.exceptions import DocumentNotFound

from argus.backend.error_handlers import APIException
from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.pytest import PytestResultTable
from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest, ArgusUserView, User
from argus.backend.plugins.loader import AVAILABLE_PLUGINS, all_plugin_models
from argus.backend.service.test_lookup import TestLookup
from argus.backend.util.common import chunk

LOGGER = logging.getLogger(__name__)


class UserViewException(APIException):
    pass


class ViewUpdateRequest(TypedDict):
    name: str
    description: str
    display_name: str
    tests: list[str]
    widget_settings: str
    plan_id: str | None


class UserViewService:
    async def create_view(self, name: str, items: list[str], widget_settings: str, user: User,
                          description: str = None, display_name: str = None, plan_id: UUID = None) -> ArgusUserView:
        try:
            name_check = await ArgusUserView.get(name=name)
            raise UserViewException(
                f"View with name {name} already exists: {name_check.id}", name, name_check, name_check.id)
        except DocumentNotFound:
            pass
        view = ArgusUserView.model_construct()
        view.name = name
        view.display_name = display_name or name
        view.description = description
        view.widget_settings = widget_settings
        view.plan_id = plan_id
        view.tests = []
        entities = await self.parse_view_entity_list(items)
        view.tests = entities["tests"]
        view.release_ids = entities["release"]
        view.group_ids = entities["group"]
        view.user_id = user.id

        await view.save()
        return view

    async def parse_view_entity_list(self, entity_list: list[str]) -> dict[str, list[str]]:
        entities = {
            "release": [],
            "group": [],
            "tests": []
        }
        for entity in entity_list:
            entity_type, entity_id = entity.split(":")
            match (entity_type):
                case "release":
                    entities["tests"].extend(t.id for t in await ArgusTest.find(release_id=UUID(entity_id)).all())
                    entities["release"].append(UUID(entity_id))
                case "group":
                    entities["tests"].extend(t.id for t in await ArgusTest.find(group_id=UUID(entity_id)).all())
                    entities["group"].append(UUID(entity_id))
                case "test":
                    entities["tests"].append(UUID(entity_id))
        return entities

    async def test_lookup(self, query: str):
        return await TestLookup.test_lookup(query)

    async def update_view(self, view_id: str | UUID, update_data: ViewUpdateRequest, user: User) -> bool:
        view_id = UUID(view_id) if isinstance(view_id, str) else view_id
        view: ArgusUserView = await ArgusUserView.get(id=view_id)
        if view.user_id != user.id and not user.is_admin():
            raise UserViewException("Unable to modify other users' views")
        for key in ["user_id", "id"]:
            update_data.pop(key, None)
        items = update_data.pop("items")
        view.name = update_data["name"]
        view.description = update_data["description"]
        view.plan_id = UUID(update_data["plan_id"]) if update_data.get("plan_id", None) else None
        view.display_name = update_data["display_name"]
        view.widget_settings = update_data["widget_settings"]
        view.tests = []
        view.release_ids = []
        view.group_ids = []
        for entity in items:
            entity_type, entity_id = entity.split(":")
            match (entity_type):
                case "release":
                    view.tests.extend(t.id for t in await ArgusTest.find(release_id=UUID(entity_id)).all())
                    view.release_ids.append(UUID(entity_id))
                case "group":
                    view.tests.extend(t.id for t in await ArgusTest.find(group_id=UUID(entity_id)).all())
                    view.group_ids.append(UUID(entity_id))
                case "test":
                    view.tests.append(UUID(entity_id))
        view.last_updated = datetime.datetime.utcnow()
        await view.save()
        return True

    async def delete_view(self, view_id: str | UUID, user: User) -> bool:
        view_id = UUID(view_id) if isinstance(view_id, str) else view_id
        view = await ArgusUserView.get(id=view_id)
        if view.user_id != user.id and not user.is_admin():
            raise UserViewException("Unable to modify other users' views")
        await view.delete()

        return True

    async def get_view(self, view_id: str | UUID) -> ArgusUserView:
        view_id = UUID(view_id) if isinstance(view_id, str) else view_id
        try:
            view: ArgusUserView = await ArgusUserView.get(id=view_id)
        except DocumentNotFound as exc:
            raise UserViewException(f"View {view_id} does not exist") from exc
        if datetime.datetime.utcnow() - (view.last_updated or datetime.datetime.fromtimestamp(0)) > datetime.timedelta(hours=1):
            await self.refresh_stale_view(view)
        return view

    async def get_view_by_name(self, view_name: str) -> ArgusUserView:
        try:
            view: ArgusUserView = await ArgusUserView.get(name=view_name)
        except DocumentNotFound as exc:
            raise UserViewException(f'View "{view_name}" does not exist') from exc
        if datetime.datetime.utcnow() - (view.last_updated or datetime.datetime.fromtimestamp(0)) > datetime.timedelta(hours=1):
            await self.refresh_stale_view(view)
        return view

    async def get_all_views(self, user: User | None = None) -> list[ArgusUserView]:
        if user:
            return list(await ArgusUserView.find(user_id=user.id).all())
        return list(await ArgusUserView.find().all())

    async def resolve_view_tests(self, view_id: str | UUID) -> list[ArgusTest]:
        view_id = UUID(view_id) if isinstance(view_id, str) else view_id
        try:
            view = await ArgusUserView.get(id=view_id)
        except DocumentNotFound as exc:
            raise UserViewException(f"View {view_id} does not exist") from exc
        return await self.resolve_tests_by_id(view.tests)

    async def resolve_tests_by_id(self, test_ids: list[str | UUID]) -> list[ArgusTest]:
        batches = await asyncio.gather(*(ArgusTest.find(id__in=batch).all() for batch in chunk(test_ids)))
        return [test for batch in batches for test in batch]

    async def batch_resolve_entity(self, entity, param_name: str, entity_ids: list[UUID]) -> list:
        batches = await asyncio.gather(
            *(entity.find(**{f"{param_name}__in": batch}).allow_filtering().all() for batch in chunk(entity_ids))
        )
        return [row for batch in batches for row in batch]

    async def refresh_stale_view(self, view: ArgusUserView):
        if view.plan_id:
            try:
                plan = await ArgusReleasePlan.get(id=view.plan_id)
            except DocumentNotFound:
                LOGGER.warning("Dangling view %s from non-existent release plan %s", view.id, view.plan_id)
                return view
            view.group_ids = plan.groups
            tests_query = self.resolve_tests_by_id(plan.tests)
        else:
            tests_query = self.resolve_view_tests(view.id)
        tests, group_tests, release_tests = await asyncio.gather(
            tests_query,
            self.batch_resolve_entity(ArgusTest, "group_id", view.group_ids),
            self.batch_resolve_entity(ArgusTest, "release_id", view.release_ids),
        )
        all_tests = {test.id for test in tests}
        all_tests.update(test.id for test in group_tests)
        all_tests.update(test.id for test in release_tests)
        view.tests = list(all_tests)
        view.last_updated = datetime.datetime.utcnow()
        await view.save()

        return view

    async def resolve_releases_for_tests(self, tests: list[ArgusTest]):
        releases = []
        unique_release_ids = reduce(lambda releases, test: releases.add(test.release_id) or releases, tests, set())
        for batch in chunk(unique_release_ids):
            releases.extend(await ArgusRelease.find(id__in=batch).all())

        return releases

    async def resolve_groups_for_tests(self, tests: list[ArgusTest]):
        releases = []
        unique_release_ids = reduce(lambda groups, test: groups.add(test.group_id) or groups, tests, set())
        for batch in chunk(unique_release_ids):
            releases.extend(await ArgusGroup.find(id__in=batch).all())

        return releases

    async def get_pytest_view_results(self, view_id: str | UUID) -> list[PytestResultTable]:
        view_id = UUID(view_id) if isinstance(view_id, str) else view_id

        view: ArgusUserView = await ArgusUserView.get(id=view_id)
        tests: list[ArgusTest] = []
        for batch in chunk(view.tests):
            tests.extend(await ArgusTest.find(id__in=batch).all())
        tests = [test for test in tests if test.plugin_name == "generic"]
        results = []
        for batch in chunk(tests):
            results.extend(
                await PytestResultTable.find(test_id__in=[t.id for t in batch]).allow_filtering().all()
            )

        return results

    async def get_versions_for_view(self, view_id: str | UUID) -> list[str]:
        tests = await self.resolve_view_tests(view_id)
        per_plugin = await asyncio.gather(
            *(plugin.get_distinct_versions_for_view(tests=tests) for plugin in all_plugin_models())
        )
        unique_versions = {ver for versions in per_plugin for ver in versions}

        return sorted(list(unique_versions), reverse=True)

    async def get_images_for_view(self, view_id: str | UUID) -> list[str]:
        tests = await self.resolve_view_tests(view_id)
        images = await AVAILABLE_PLUGINS["scylla-cluster-tests"].model.get_distinct_cloud_images_for_view(tests)

        return images

    async def resolve_view_for_edit(self, view_id: str | UUID) -> dict:
        view_id = UUID(view_id) if isinstance(view_id, str) else view_id
        view: ArgusUserView = await ArgusUserView.get(id=view_id)
        resolved = view.model_dump()
        view_groups = await self.batch_resolve_entity(ArgusGroup, "id", view.group_ids)
        view_releases = await self.batch_resolve_entity(ArgusRelease, "id", view.release_ids)
        view_tests = await self.resolve_view_tests(view.id)
        all_groups = {group.id: partial(TestLookup.index_mapper, type="group")(group)
                      for group in await self.resolve_releases_for_tests(view_tests)}
        all_releases = {release.id: partial(TestLookup.index_mapper, type="release")(release)
                        for release in await self.resolve_releases_for_tests(view_tests)}
        entities_by_id = {
            entity.id: partial(TestLookup.index_mapper, type="release" if isinstance(
                entity, ArgusRelease) else "group")(entity)
            for container in [view_releases, view_groups]
            for entity in container
        }

        items = []
        for test in view_tests:
            if not (entities_by_id.get(test.group_id) or entities_by_id.get(test.release_id)):
                item = test.model_dump()
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
