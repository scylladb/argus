import re
from dataclasses import dataclass
from uuid import UUID

from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest
from argus.backend.service.chat.entity import ChatEntity
from argus.backend.service.testrun import TestRunService
from argus.backend.service.views import UserViewService
from argus.backend.util.common import gather_limited, select_rows

CANDIDATE_LIMIT = 10
EXPANSION_LIMIT = 50
RECENT_BUILDS = 5
JENKINS_URL = re.compile(r"^https?://[^/]+(?P<path>(?:/job/[^/]+)+)(?:/(?P<number>\d+))?(?:/.*)?$")
BUILD_SUFFIX = re.compile(r"^(?P<reference>.+?)\s*#\s*(?P<number>\d+)$")
RUN_HINT = "a run id, build_id#number, a test reference with #number, or a Jenkins build URL"


class ToolScopeError(Exception):
    pass


class TestReferenceError(Exception):
    pass


def _same(reference: str, *names: str | None) -> bool:
    wanted = reference.strip().lower()
    return any(name and wanted == name.strip().lower() for name in names)


def _as_uuid(reference: str) -> UUID | None:
    try:
        return UUID(reference.strip())
    except ValueError:
        return None


def jenkins_path(reference: str) -> tuple[str, int | None] | None:
    """The job path and the build number of a Jenkins job or build URL."""
    match = JENKINS_URL.match(reference.strip())
    if not match:
        return None
    path = "/".join(part for part in match.group("path").split("/job/") if part)
    return path, int(match.group("number")) if match.group("number") else None


@dataclass(slots=True)
class Scope:
    releases: dict[UUID, ArgusRelease]
    groups: dict[UUID, ArgusGroup]
    tests: list[ArgusTest]

    def group_name(self, test: ArgusTest) -> str:
        group = self.groups.get(test.group_id)
        return group.name if group else "?"

    def label(self, test: ArgusTest) -> str:
        return f"{self.group_name(test)}/{test.name}"

    def release_named(self, name: str) -> ArgusRelease:
        return resolve_release(self, name)

    def find_releases(self, reference: str) -> list[ArgusRelease]:
        if (uuid := _as_uuid(reference)) and uuid in self.releases:
            return [self.releases[uuid]]
        return [release for release in self.releases.values()
                if _same(reference, release.name, release.pretty_name)]

    def find_groups(self, reference: str) -> list[ArgusGroup]:
        if (uuid := _as_uuid(reference)) and uuid in self.groups:
            return [self.groups[uuid]]
        exact = [group for group in self.groups.values()
                 if group.build_system_id and group.build_system_id == reference.strip()]
        if exact:
            return exact
        release_part, _, group_part = reference.rpartition("/")
        return [group for group in self.groups.values()
                if _same(group_part, group.name, group.pretty_name)
                and (not release_part or self._release_is(group.release_id, release_part))]

    def find_tests(self, reference: str) -> list[ArgusTest]:
        reference = reference.strip()
        if (uuid := _as_uuid(reference)) is not None:
            return [test for test in self.tests if test.id == uuid]
        if jenkins := jenkins_path(reference):
            reference = jenkins[0]
        exact = [test for test in self.tests if test.build_system_id and test.build_system_id == reference]
        if exact:
            return exact
        parts = reference.split("/")
        test_part = parts[-1]
        group_part = parts[-2] if len(parts) >= 2 else None
        release_part = "/".join(parts[:-2]) if len(parts) >= 3 else None
        matches = []
        for test in self.tests:
            if not _same(test_part, test.name, test.pretty_name):
                continue
            group = self.groups.get(test.group_id)
            if group_part and not (group and _same(group_part, group.name, group.pretty_name)):
                continue
            if release_part and not self._release_is(test.release_id, release_part):
                continue
            matches.append(test)
        return matches

    def _release_is(self, release_id: UUID, reference: str) -> bool:
        release = self.releases.get(release_id)
        return bool(release) and _same(reference, release.name, release.pretty_name)

    def enabled_tests(self, *, group: ArgusGroup | None = None, release: ArgusRelease | None = None) -> list[ArgusTest]:
        tests = [test for test in self.tests
                 if test.enabled and (group is None or test.group_id == group.id)
                 and (release is None or test.release_id == release.id)
                 and getattr(self.groups.get(test.group_id), "enabled", True)]
        return sorted(tests, key=self.label)


def _one(found: list, reference: str, kind: str, describe):
    if len(found) == 1:
        return found[0]
    if found:
        candidates = ", ".join(describe(item) for item in found[:CANDIDATE_LIMIT])
        raise TestReferenceError(f"{reference} matches several {kind}s: {candidates}. Be more precise.")
    raise TestReferenceError(f"No {kind} {reference} in this chat's scope")


def resolve_release(scope: Scope, reference: str) -> ArgusRelease:
    return _one(scope.find_releases(reference), reference, "release", lambda release: release.name)


def resolve_group(scope: Scope, reference: str) -> ArgusGroup:
    return _one(scope.find_groups(reference), reference, "group",
                lambda group: f"{scope.releases[group.release_id].name}/{group.name}"
                if group.release_id in scope.releases else group.name)


def resolve_test_reference(scope: Scope, reference: str) -> ArgusTest:
    """One test of the scope, by id, build_system_id, Jenkins job URL, name or pretty name, optionally
    prefixed by its group and its release ("release/group/test")."""
    found = scope.find_tests(reference)
    if not found and (scope.find_groups(reference) or scope.find_releases(reference)):
        raise TestReferenceError(f"{reference} is a group or a release; name one of its tests")
    return _one(found, reference, "test", scope.label)


def resolve_tests(scope: Scope, references: list[str]) -> list[ArgusTest]:
    """Tests for each reference; a group or a release stands for its enabled tests."""
    selected: dict[UUID, ArgusTest] = {}
    for reference in references:
        tests = scope.find_tests(reference)
        if len(tests) > 1:
            _one(tests, reference, "test", scope.label)
        if not tests and (groups := scope.find_groups(reference)):
            tests = scope.enabled_tests(group=_one(groups, reference, "group", lambda group: group.name))
        elif not tests and (releases := scope.find_releases(reference)):
            tests = scope.enabled_tests(release=_one(releases, reference, "release", lambda release: release.name))
        elif not tests:
            raise TestReferenceError(f"No test, group or release {reference} in this chat's scope")
        selected.update((test.id, test) for test in tests if test.id not in selected)
        if len(selected) > EXPANSION_LIMIT:
            raise TestReferenceError(f"That is more than {EXPANSION_LIMIT} tests; name fewer tests or groups")
    return list(selected.values())


async def load_scope(entity: ChatEntity) -> Scope:
    releases = [release for release in await gather_limited(
        ArgusRelease.find_one(id=release_id) for release_id in entity.release_ids) if release]
    group_batches = await gather_limited(ArgusGroup.find(release_id=release.id).all() for release in releases)
    groups = {group.id: group for batch in group_batches for group in batch}
    if entity.test_ids is None:
        test_batches = await gather_limited(ArgusTest.find(release_id=release.id).all() for release in releases)
        tests = [test for batch in test_batches for test in batch]
    else:
        tests = await UserViewService().resolve_tests_by_id(list(entity.test_ids))
    return Scope(releases={release.id: release for release in releases}, groups=groups, tests=tests)


def run_url(run) -> str:
    """The Argus page of a run: by its Jenkins build when it has one, otherwise by its plugin."""
    if run.build_id and run.build_number:
        return f"/test/{run.build_id}/{run.build_number}"
    return f"/tests/{type(run)._plugin_name}/{run.id}"


async def run_in_scope(entity: ChatEntity, run_id: UUID):
    service = TestRunService()
    run_type = await service.get_test_type_for_run(run_id)
    run = await service.get_run(run_type, run_id) if run_type in service.plugins else None
    if run is None:
        raise TestReferenceError(f"Run {run_id} not found")
    if not entity.reaches_release(run.release_id) or not entity.reaches_test(run.test_id):
        raise ToolScopeError(f"Run {run_id} is outside {entity.name}")
    return run


async def _recent_builds(test: ArgusTest) -> str:
    plugin = TestRunService().get_plugin(plugin_name=test.plugin_name)
    if plugin is None:
        return "none"
    rows = await select_rows(plugin.model.find(build_id=test.build_system_id).limit(RECENT_BUILDS),
                             "build_number", "status")
    return ", ".join(f"#{row['build_number']} ({row['status']})" for row in rows) or "none"


async def resolve_run_reference(entity: ChatEntity, scope: Scope, reference: str):
    """One run, by id, build_id#number, any test reference with #number, or a Jenkins build URL."""
    reference = reference.strip()
    if (uuid := _as_uuid(reference)) is not None:
        return await run_in_scope(entity, uuid)
    jenkins = jenkins_path(reference)
    if jenkins and jenkins[1] is not None:
        test_reference, number = jenkins[0], jenkins[1]
    elif match := BUILD_SUFFIX.match(reference):
        test_reference, number = match.group("reference"), int(match.group("number"))
    else:
        test = resolve_test_reference(scope, reference)
        raise TestReferenceError(f"{reference} names a test, not a run. Name {RUN_HINT}. The latest builds of "
                                 f"{scope.label(test)}: {await _recent_builds(test)}")
    test = resolve_test_reference(scope, test_reference)
    run = await TestRunService().get_run_by_build_number(test.build_system_id, number)
    if run is None:
        raise TestReferenceError(f"{scope.label(test)} has no build #{number} in Argus. Its latest builds: "
                                 f"{await _recent_builds(test)}")
    return await run_in_scope(entity, run.id)
