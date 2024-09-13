


from functools import partial
import re
from urllib.parse import unquote
from typing import Callable
from uuid import UUID

from cassandra.cqlengine.models import Model
from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest


class TestLookup:
    ADD_ALL_ID = UUID("db6f33b2-660b-4639-ba7f-79725ef96616")
    
    @classmethod
    def index_mapper(cls, item: Model, type = "test"):
        mapped = dict(item)
        mapped["type"] = type
        return mapped

    @classmethod
    def explode_group(cls, group_id: UUID | str):
        group = ArgusGroup.get(id=group_id)
        release = ArgusRelease.get(id=group.release_id)
        tests = ArgusTest.filter(group_id=group.id).all()

        exploded = []
        for test in tests:
            test = cls.index_mapper(test)
            test["group"] = group.pretty_name or group.name
            test["release"] = release.name
            test["name"] = test["pretty_name"] or test["name"]
            exploded.append(test)

        return exploded

    @classmethod
    def test_lookup(cls, query: str, release_id: UUID | str = None):
        def check_visibility(entity: dict):
            if entity["type"] == "release" and release_id:
                return False
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


        if release_id:
            all_releases = [ArgusRelease.get(id=release_id)]
        else:
            all_releases = ArgusRelease.objects().limit(None)
        all_tests = ArgusTest.objects().limit(None)
        all_groups = ArgusGroup.objects().limit(None)
        if release_id:
            all_tests = all_tests.filter(release_id=release_id)
            all_groups = all_groups.filter(release_id=release_id)
        release_by_id = {release.id: partial(cls.index_mapper, type="release")(release) for release in all_releases}
        group_by_id = {group.id: partial(cls.index_mapper, type="group")(group) for group in all_groups}
        index = [cls.index_mapper(t) for t in all_tests]
        index = [*release_by_id.values(), *group_by_id.values(), *index]
        for item in index:
            item["group"] = group_by_id.get(item.get("group_id"))
            item["release"] = release_by_id.get(item.get("release_id"))

        results = filter(partial(search_func, query=text_query), index)

        return [{ "id": cls.ADD_ALL_ID, "name": "Add all...", "type": "special" }, *list(res for res in results if check_visibility(res))]