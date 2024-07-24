import datetime
import logging
import re
from functools import partial, reduce
from typing import Any, Callable, TypedDict
from urllib.parse import unquote
from uuid import UUID

from cassandra.cqlengine.models import Model
from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest, ArgusUserView, User
from argus.backend.plugins.loader import all_plugin_models
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


class UserViewService:
    ADD_ALL_ID = UUID("db6f33b2-660b-4639-ba7f-79725ef96616")
    def create_view(self, name: str, items: list[str], widget_settings: str, description: str = None, display_name: str = None) -> ArgusUserView:
        try:
            name_check = ArgusUserView.get(name=name)
            raise UserViewException(f"View with name {name} already exists: {name_check.id}", name, name_check, name_check.id)
        except ArgusUserView.DoesNotExist:
            pass
        view = ArgusUserView()
        view.name = name
        view.display_name = display_name or name
        view.description = description
        view.widget_settings = widget_settings
        view.tests = []
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
        view.user_id = current_user().id

        view.save()
        return view

    @staticmethod
    def index_mapper(item: Model, type = "test"):
        mapped = dict(item)
        mapped["type"] = type
        return mapped

    def test_lookup(self, query: str):
        def check_visibility(entity: dict):
            if not entity["enabled"]:
                return False
            if entity.get("group") and not entity["group"]["enabled"]:
                return False
            if entity.get("release") and not entity["release"]["enabled"]:
                return False
            return True

        def facet_extraction(query: str) -> str:
            extractor = re.compile(r"(?:(?P<name>(?:release|group|type)):(?P<value>\"?[\w\d\.\-]*\"?))")
            facets = re.findall(extractor, query)

            return (re.sub(extractor, "", query).strip(), facets)

        def type_facet_filter(item: dict, key: str, facet_query: str):
            entity_type: str = item[key]
            return facet_query.lower() == entity_type

        def facet_filter(item: dict, key: str, facet_query: str):
            if entity := item.get(key):
                name: str = entity.get("pretty_name") or entity.get("name")
                return facet_query.lower() in name.lower() if name else False
            return False

        def facet_wrapper(query_func: Callable[[dict], bool], facet_query: str, facet_type: str) -> bool:
            def inner(item: dict, query: str):
                return query_func(item, query) and facet_funcs[facet_type](item, facet_type, facet_query)
            return inner

        facet_funcs = {
            "type": type_facet_filter,
            "release": facet_filter,
            "group": facet_filter,
        }

        def index_searcher(item, query: str):
            name: str = item["pretty_name"] or item["name"]
            return unquote(query).lower() in name.lower() if query else True

        text_query, facets = facet_extraction(query)
        search_func = index_searcher
        for facet, value in facets:
            if facet in facet_funcs.keys():
                search_func = facet_wrapper(query_func=search_func, facet_query=value, facet_type=facet)


        all_tests = ArgusTest.objects().limit(None)
        all_releases = ArgusRelease.objects().limit(None)
        all_groups = ArgusGroup.objects().limit(None)
        release_by_id = {release.id: partial(self.index_mapper, type="release")(release) for release in all_releases}
        group_by_id = {group.id: partial(self.index_mapper, type="group")(group) for group in all_groups}
        index = [self.index_mapper(t) for t in all_tests]
        index = [*release_by_id.values(), *group_by_id.values(), *index]
        for item in index:
            item["group"] = group_by_id.get(item.get("group_id"))
            item["release"] = release_by_id.get(item.get("release_id"))

        results = filter(partial(search_func, query=text_query), index)

        return [{ "id": self.ADD_ALL_ID, "name": "Add all...", "type": "special" }, *list(res for res in results if check_visibility(res))]

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
        view.tests = [test.id for test in self.resolve_view_tests(view.id)]
        all_tests = set(view.tests)
        all_tests.update(test.id for test in self.batch_resolve_entity(ArgusTest, "group_id", view.group_ids))
        all_tests.update(test.id for test in self.batch_resolve_entity(ArgusTest, "release_id", view.release_ids))
        view.tests = list(all_tests)
        view.last_updated = datetime.datetime.utcnow()
        view.save()

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

    def get_versions_for_view(self, view_id: str | UUID) -> list[str]:
        tests = self.resolve_view_tests(view_id)
        unique_versions = {ver for plugin in all_plugin_models()
                           for ver in plugin.get_distinct_versions_for_view(tests=tests)}

        return sorted(list(unique_versions), reverse=True)

    def resolve_view_for_edit(self, view_id: str | UUID) -> dict:
        view: ArgusUserView = ArgusUserView.get(id=view_id)
        resolved = dict(view)
        view_groups = self.batch_resolve_entity(ArgusGroup, "id", view.group_ids)
        view_releases = self.batch_resolve_entity(ArgusRelease, "id", view.release_ids)
        view_tests = self.resolve_view_tests(view.id)
        all_groups = { group.id: partial(self.index_mapper, type="group")(group) for group in self.resolve_releases_for_tests(view_tests) }
        all_releases ={ release.id: partial(self.index_mapper, type="release")(release) for release in self.resolve_releases_for_tests(view_tests) }
        entities_by_id = {
            entity.id: partial(self.index_mapper, type="release" if isinstance(entity, ArgusRelease) else "group")(entity)
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
            entity["group"] = all_groups.get(entity.get("group_id"), {}).get("pretty_name") or all_groups.get(entity.get("group_id"), {}).get("name")
            entity["release"] = all_releases.get(entity.get("release_id"), {}).get("pretty_name") or all_releases.get(entity.get("release_id"), {}).get("name")

        resolved["items"] = items
        return resolved
