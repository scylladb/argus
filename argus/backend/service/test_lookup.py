import asyncio
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import unquote
from uuid import UUID

from coodie.aio import Document
from coodie.exceptions import DocumentNotFound

from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest, User
from argus.backend.plugins.core import PluginModelBase
from argus.backend.plugins.loader import all_plugin_models
from argus.backend.service.issue_service import IssueService, IssueServiceException
from argus.backend.service.stats import ReleaseStatsCollector
from argus.backend.util.common import select_rows, version_key
from argus.common.enums import TestInvestigationStatus, TestStatus

INDEX_TTL = 60
STATS_FACETS = ("status", "istatus", "assignee")
FACET_KEYS = ("release", "group", "type", "issue", *STATS_FACETS)
TYPE_ORDER = {"release": 0, "group": 1, "test": 2}
TOKEN = re.compile(r'(?:"[^"]*"?|[^\s"])+')
JOB_SEGMENT = re.compile(r"/job/([^/?#]+)")
RELEASE_COLUMNS = ("id", "name", "pretty_name", "enabled", "priority", "dormant")
GROUP_COLUMNS = ("id", "release_id", "name", "pretty_name", "build_system_id", "enabled")
GROUP_REF_KEYS = ("id", "name", "pretty_name", "enabled")
TEST_COLUMNS = ("id", "release_id", "group_id", "name", "pretty_name", "build_system_id", "enabled", "test_metadata")


@dataclass(slots=True, frozen=True)
class ParsedQuery:
    terms: tuple[str, ...]
    excluded_terms: tuple[str, ...]
    facets: dict[str, tuple[str, ...]]
    excluded_facets: dict[str, tuple[str, ...]]
    uuid: UUID | None
    issue_key: str | None


@dataclass(slots=True, frozen=True)
class IndexEntry:
    id: UUID
    type: str
    name: str
    pretty_name: str | None
    release_id: UUID | None
    group_id: UUID | None
    build_system_id: str | None
    enabled: bool
    test_metadata: dict | None
    haystack: str


@dataclass(slots=True, frozen=True)
class StatsFacts:
    status: str
    investigation_status: str
    assignee: str | None


@dataclass(slots=True, frozen=True)
class StatsLookup:
    facts: dict[str, StatsFacts]
    user_names: dict[str, str]


@dataclass(slots=True, frozen=True)
class SearchIndex:
    entries: list[IndexEntry]
    by_id: dict[UUID, IndexEntry]
    releases: dict[UUID, dict]
    groups: dict[UUID, dict]
    built_at: float


def _tokenize(query: str) -> list[tuple[str, int]]:
    # Each token keeps the length of the part typed before its first quote:
    # a "-" or a facet key counts only there, so quoted text stays literal.
    tokens = []
    for match in TOKEN.finditer(query):
        raw = match.group()
        quote = raw.find('"')
        tokens.append((raw.replace('"', ""), len(raw) if quote < 0 else quote))
    return tokens


def _job_path(token: str) -> str | None:
    if not token.startswith(("http://", "https://")):
        return None
    return "/".join(JOB_SEGMENT.findall(token)) or None


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _single_uuid(tokens: list[tuple[str, int]]) -> UUID | None:
    if len(tokens) != 1:
        return None
    try:
        return UUID(tokens[0][0])
    except ValueError:
        return None


def parse_query(query: str) -> ParsedQuery:
    tokens = _tokenize(query)
    terms, excluded_terms = [], []
    facets, excluded_facets = defaultdict(list), defaultdict(list)
    for text, bare_length in tokens:
        negated = bare_length > 0 and text.startswith("-") and text.strip("-") != ""
        if negated:
            text, bare_length = text[1:], bare_length - 1
        key, colon, value = text.partition(":")
        if colon and len(key) < bare_length and key.lower() in FACET_KEYS:
            if value:
                (excluded_facets if negated else facets)[key.lower()].append(value.lower())
        elif text:
            (excluded_terms if negated else terms).append(unquote(_job_path(text) or text).lower())
    issue_keys = facets.pop("issue", [])
    excluded_facets.pop("issue", None)
    return ParsedQuery(
        terms=_unique(terms),
        excluded_terms=_unique(excluded_terms),
        facets={key: _unique(values) for key, values in facets.items()},
        excluded_facets={key: _unique(values) for key, values in excluded_facets.items()},
        uuid=_single_uuid(tokens),
        issue_key=issue_keys[0] if issue_keys else None,
    )


def _entry(entry_type: str, row: dict, release_id: UUID | None = None, group_id: UUID | None = None,
           test_metadata: dict | None = None) -> IndexEntry:
    build_system_id = row.get("build_system_id")
    return IndexEntry(
        id=row["id"],
        type=entry_type,
        name=row["name"],
        pretty_name=row["pretty_name"],
        release_id=release_id,
        group_id=group_id,
        build_system_id=build_system_id,
        enabled=row["enabled"],
        test_metadata=test_metadata,
        haystack="\n".join(part for part in (row["name"], row["pretty_name"], build_system_id) if part).lower(),
    )


def _index_rows(releases: list[dict], groups: list[dict], tests: list[dict]) -> SearchIndex:
    release_refs = {release["id"]: {**release, "priority": release["priority"] or 0} for release in releases}
    group_refs = {group["id"]: {key: group[key] for key in GROUP_REF_KEYS} for group in groups}
    # Point each row at its parent's UUID object instead of a copy per row, to keep the index small.
    release_ids = {release_id: release_id for release_id in release_refs}
    group_ids = {group_id: group_id for group_id in group_refs}
    entries = [
        *(_entry("release", release) for release in releases),
        *(_entry("group", group, release_id=release_ids.get(group["release_id"], group["release_id"]))
          for group in groups),
        *(_entry("test", test, release_id=release_ids.get(test["release_id"], test["release_id"]),
                 group_id=group_ids.get(test["group_id"], test["group_id"]),
                 test_metadata=dict(test["test_metadata"]) if test["test_metadata"] else None)
          for test in tests),
    ]
    index = SearchIndex(
        entries=entries,
        by_id={entry.id: entry for entry in entries},
        releases=release_refs,
        groups=group_refs,
        built_at=time.monotonic(),
    )
    entries.sort(key=lambda entry: _order_key(entry, index))
    return index


async def _build_index() -> SearchIndex:
    releases, groups, tests = await asyncio.gather(
        select_rows(ArgusRelease.find(), *RELEASE_COLUMNS),
        select_rows(ArgusGroup.find(), *GROUP_COLUMNS),
        select_rows(ArgusTest.find(), *TEST_COLUMNS),
    )
    return await asyncio.to_thread(_index_rows, releases, groups, tests)


def _is_stale(index: SearchIndex | None) -> bool:
    return index is None or time.monotonic() - index.built_at >= INDEX_TTL


def _own_release(entry: IndexEntry, index: SearchIndex) -> dict | None:
    return index.releases.get(entry.id if entry.type == "release" else entry.release_id)


def _own_group(entry: IndexEntry, index: SearchIndex) -> dict | None:
    return index.groups.get(entry.id if entry.type == "group" else entry.group_id)


def _in_scope(entry: IndexEntry, release_id: UUID | None) -> bool:
    return release_id is None or (entry.type != "release" and entry.release_id == release_id)


def _status_scope(release_id: UUID | None, parsed: ParsedQuery, index: SearchIndex) -> dict | None:
    if release_id:
        return index.releases.get(release_id)
    values = parsed.facets.get("release", ())
    named = [release for release in index.releases.values()
             if any(value in release["name"].lower() or value in (release["pretty_name"] or "").lower()
                    for value in values)]
    exact = [release for release in named
             if any(value in (release["name"].lower(), (release["pretty_name"] or "").lower()) for value in values)]
    return next((candidates[0] for candidates in (exact, named) if len(candidates) == 1), None)


def _latest_assignee(test: dict) -> str | None:
    assignee = test["last_runs"][0].get("assignee") if test["last_runs"] else None
    return str(assignee) if assignee else None


def stats_facts(stats: dict) -> dict[str, StatsFacts]:
    if stats.get("dormant"):
        return {}
    return {
        test_id: StatsFacts(
            status=TestStatus(test["status"]).value,
            investigation_status=TestInvestigationStatus(test["investigation_status"]).value,
            assignee=_latest_assignee(test),
        )
        for group in stats["groups"].values() for test_id, test in group["tests"].items()
    }


async def _stats_lookup(release: dict, parsed: ParsedQuery) -> StatsLookup:
    stats = await ReleaseStatsCollector(release_name=release["name"]).collect(
        limited=False, force=False, include_no_version=True)
    user_names = {}
    if "assignee" in parsed.facets or "assignee" in parsed.excluded_facets:
        users = await select_rows(User.find(), "id", "username", "full_name")
        user_names = {str(user["id"]): f"{user['username']}\n{user['full_name'] or ''}".lower() for user in users}
    return StatsLookup(facts=stats_facts(stats), user_names=user_names)


def _visible(entry: IndexEntry, index: SearchIndex) -> bool:
    group = index.groups.get(entry.group_id)
    release = index.releases.get(entry.release_id)
    return entry.enabled and (group is None or group["enabled"]) and (release is None or release["enabled"])


def _stats_facet_matches(facts: StatsFacts | None, key: str, value: str, user_names: dict[str, str]) -> bool:
    if facts is None:
        return False
    if key == "status":
        return facts.status.startswith(value)
    if key == "istatus":
        return facts.investigation_status.startswith(value)
    return facts.assignee is not None and value in user_names.get(facts.assignee, "")


def _facet_matches(entry: IndexEntry, key: str, value: str, index: SearchIndex, stats: StatsLookup | None) -> bool:
    if key == "type":
        return entry.type == value
    if key in STATS_FACETS:
        return stats is not None and _stats_facet_matches(stats.facts.get(str(entry.id)), key, value, stats.user_names)
    ref = _own_release(entry, index) if key == "release" else _own_group(entry, index)
    return ref is not None and (value in ref["name"].lower() or value in (ref["pretty_name"] or "").lower())


def _matches(entry: IndexEntry, parsed: ParsedQuery, index: SearchIndex, stats: StatsLookup | None) -> bool:
    if stats is not None and entry.type != "test":
        return False
    haystack = entry.haystack
    if not all(term in haystack for term in parsed.terms):
        return False
    if any(term in haystack for term in parsed.excluded_terms):
        return False
    if not _visible(entry, index):
        return False
    if not all(any(_facet_matches(entry, key, value, index, stats) for value in values)
               for key, values in parsed.facets.items()):
        return False
    return not any(_facet_matches(entry, key, value, index, stats)
                   for key, values in parsed.excluded_facets.items() for value in values)


def _match_tier(term: str, display: str) -> int:
    if not term or display == term:
        return 0
    if display.startswith(term):
        return 1
    position = display.find(term)
    tier = 3 if position >= 0 else 4
    while position > 0:
        if not display[position - 1].isalnum():
            return 2
        position = display.find(term, position + 1)
    return tier


def _order_key(entry: IndexEntry, index: SearchIndex) -> tuple:
    release = _own_release(entry, index) or {}
    return (
        TYPE_ORDER[entry.type],
        release.get("dormant", False),
        -release.get("priority", 0),
        version_key(entry.pretty_name or entry.name),
        str(entry.id),
    )


def _issue_run_hit(link: dict, index: SearchIndex) -> dict:
    test = index.by_id.get(link["test_id"])
    release_id = test.release_id if test else None
    group_id = test.group_id if test else None
    return {
        "id": link["run_id"],
        "type": "run",
        "name": f"{link['test_name']}#{link['build_number']}",
        "pretty_name": None,
        "build_system_id": link["build_id"],
        "enabled": test.enabled if test else False,
        "status": link["status"],
        "start_time": link["start_time"],
        "build_number": link["build_number"],
        "test_id": link["test_id"],
        "release_id": release_id,
        "group_id": group_id,
        "test": {"id": link["test_id"], "name": link["test_name"]},
        "release": index.releases.get(release_id),
        "group": index.groups.get(group_id),
    }


def _to_hit(entry: IndexEntry, index: SearchIndex) -> dict:
    return {
        "id": entry.id,
        "type": entry.type,
        "name": entry.name,
        "pretty_name": entry.pretty_name,
        "build_system_id": entry.build_system_id,
        "enabled": entry.enabled,
        "test_metadata": entry.test_metadata or {},
        "release_id": entry.release_id,
        "group_id": entry.group_id,
        "release": index.releases.get(entry.release_id),
        "group": index.groups.get(entry.group_id),
    }


class TestLookup:
    __test__ = False
    ADD_ALL_ID = UUID("db6f33b2-660b-4639-ba7f-79725ef96616")
    _index: SearchIndex | None = None
    _index_lock: asyncio.Lock | None = None
    _index_lock_loop: int | None = None

    @classmethod
    def index_mapper(cls, item: Document, type="test"):
        mapped = item.model_dump()
        mapped["type"] = type
        return mapped

    @classmethod
    async def explode_group(cls, group_id: UUID | str):
        group_id = UUID(group_id) if isinstance(group_id, str) else group_id
        group = await ArgusGroup.get(id=group_id)
        release = await ArgusRelease.get(id=group.release_id)
        tests = await ArgusTest.find(group_id=group.id).all()

        exploded = []
        for test in tests:
            test = cls.index_mapper(test)
            test["group"] = group.pretty_name or group.name
            test["release"] = release.name
            test["name"] = test["pretty_name"] or test["name"]
            exploded.append(test)

        return exploded

    @classmethod
    async def find_run(cls, run_id: UUID) -> PluginModelBase | None:
        runs = await asyncio.gather(*(model.find_one(id=run_id) for model in all_plugin_models()))
        return next((run for run in runs if run is not None), None)

    @classmethod
    async def resolve_run_test(cls, test_id: UUID) -> ArgusTest:
        try:
            test = await ArgusTest.get(id=test_id)
            return test
        except DocumentNotFound:
            return None

    @classmethod
    async def resolve_run_group(cls, group_id: UUID) -> ArgusGroup:
        try:
            group = await ArgusGroup.get(id=group_id)
            return group
        except DocumentNotFound:
            return None

    @classmethod
    async def resolve_run_release(cls, run_test_id: UUID) -> ArgusRelease:
        try:
            release = await ArgusRelease.get(id=run_test_id)
            return release
        except DocumentNotFound:
            return None

    @classmethod
    async def _dump_resolved(cls, resolver: Callable[[UUID], Awaitable[Document | None]],
                             entity_id: UUID | None) -> dict | None:
        entity = await resolver(entity_id) if entity_id else None
        return entity.model_dump() if entity else None

    @classmethod
    async def make_single_run_response(cls, run_id: UUID) -> list[dict[str, Any]]:
        run = await cls.find_run(run_id)
        if run:
            run = run.model_dump()
            run["type"] = "run"
            run["test"], run["group"], run["release"] = await asyncio.gather(
                cls._dump_resolved(cls.resolve_run_test, run["test_id"]),
                cls._dump_resolved(cls.resolve_run_group, run["group_id"]),
                cls._dump_resolved(cls.resolve_run_release, run["release_id"]),
            )
            test_name = run["test"]["name"] if run["test"] else ""
            run["name"] = f"{test_name}#{run['build_number']}"

            return [run]

        return []

    @classmethod
    def _lock(cls) -> asyncio.Lock:
        loop_id = id(asyncio.get_running_loop())
        if cls._index_lock is None or cls._index_lock_loop != loop_id:
            cls._index_lock, cls._index_lock_loop = asyncio.Lock(), loop_id
        return cls._index_lock

    @classmethod
    async def _get_index(cls) -> SearchIndex:
        index = cls._index
        if _is_stale(index):
            async with cls._lock():
                index = cls._index
                if _is_stale(index):
                    index = cls._index = await _build_index()
        return index

    @classmethod
    def clear_index(cls) -> None:
        cls._index = None

    @classmethod
    async def _lookup_issue(cls, key: str, index: SearchIndex) -> list[dict]:
        try:
            result = await IssueService().get_issue_links(key)
        except IssueServiceException:
            return []
        return [_issue_run_hit(link, index) for link in result["links"]]

    @classmethod
    async def _lookup_uuid(cls, entity_id: UUID, index: SearchIndex) -> list[dict]:
        if entry := index.by_id.get(entity_id):
            return [_to_hit(entry, index)]
        return await cls.make_single_run_response(entity_id)

    @classmethod
    async def test_lookup(cls, query: str, release_id: UUID | str | None = None,
                          limit: int | None = None, offset: int = 0) -> tuple[list[dict], int]:
        if isinstance(release_id, str):
            release_id = UUID(release_id) if release_id else None
        parsed = parse_query(query)
        index = await cls._get_index()
        if parsed.issue_key or parsed.uuid:
            if parsed.issue_key:
                hits = await cls._lookup_issue(parsed.issue_key, index)
            else:
                hits = await cls._lookup_uuid(parsed.uuid, index)
            return (hits if limit is None else hits[offset:offset + limit]), len(hits)

        stats_query = any(key in parsed.facets or key in parsed.excluded_facets for key in STATS_FACETS)
        scope = _status_scope(release_id, parsed, index) if stats_query else None
        stats = await _stats_lookup(scope, parsed) if scope else None
        matches = [] if stats_query and scope is None else [
            entry for entry in index.entries
            if _in_scope(entry, release_id) and _matches(entry, parsed, index, stats)
        ]
        first_term = parsed.terms[0] if parsed.terms else ""
        # The entries are stored in _order_key order and the sort is stable, so ties keep that order.
        ranked = sorted(matches, key=lambda entry: _match_tier(first_term, (entry.pretty_name or entry.name).lower()))
        if limit is None:
            add_all = {"id": cls.ADD_ALL_ID, "name": "Add all...", "type": "special"}
            return [add_all, *(_to_hit(entry, index) for entry in ranked)], len(matches)
        return [_to_hit(entry, index) for entry in ranked[offset:offset + limit]], len(matches)
