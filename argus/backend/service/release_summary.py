import asyncio
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, TypedDict
from uuid import UUID

from cassandra import DriverException
from cassandra.cluster import NoHostAvailable
from coodie.exceptions import DocumentNotFound

from argus.backend.error_handlers import APIException
from argus.backend.models.github_issue import GithubIssue, IssueLink
from argus.backend.models.jira import JiraIssue
from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.release_summary import ROLLUP_VERSION, ReleaseSummary
from argus.backend.models.web import ArgusGroup, ArgusRelease, ArgusTest, ArgusTestRunComment
from argus.backend.plugins.loader import all_plugin_models
from argus.backend.service.views import UserViewService
from argus.backend.util.common import chunk, gather_limited, select_rows
from argus.common.enums import TestStatus
from argus.common.versions import ScyllaVersion, parse_version

LOGGER = logging.getLogger(__name__)

PENDING = "pending"
PASSED = {TestStatus.PASSED.value}
FAILED = {TestStatus.FAILED.value, TestStatus.TEST_ERROR.value, TestStatus.ERROR.value}
ABORTED = {TestStatus.ABORTED.value}
IN_PROGRESS = {TestStatus.CREATED.value, TestStatus.RUNNING.value}
FINAL = PASSED | FAILED | ABORTED
LAST = datetime.max.replace(tzinfo=UTC)
FIRST_LINK_READS = 20


class ReleaseSummaryException(APIException):
    pass


class Counts(TypedDict):
    executed: int
    passed: int
    failed: int
    aborted: int
    in_progress: int
    pending: int
    issues_new: int
    issues_existing: int
    issues_fixed: int


class TestEntry(TypedDict):
    test_id: str
    group_id: str
    test_name: str
    group_name: str
    status: str
    run_id: str | None
    build_id: str | None
    build_number: int | None
    version: str | None
    issues: int
    comments: int
    start_time: str | None


class IssueEntry(TypedDict):
    id: str
    type: Literal["jira", "github"]
    key: str
    title: str | None
    url: str | None
    state: str | None
    novelty: Literal["new", "existing"]
    status: Literal["open", "fixed"]
    on_latest_run: bool
    open_test_ids: list[str]
    latest_test_ids: list[str]
    test_ids: list[str]
    run_ids: list[str]
    issue: dict


class Summary(TypedDict):
    version: str | None
    counts: Counts
    tests: list[TestEntry]
    issues: list[IssueEntry]


@dataclass(frozen=True, slots=True)
class SummaryRun:
    id: UUID
    test_id: UUID
    build_id: str
    build_number: int | None
    status: str
    start_time: datetime
    version: ScyllaVersion


@dataclass(slots=True)
class ReleaseData:
    runs: list[SummaryRun]
    tests: dict[UUID, ArgusTest]
    groups: dict[UUID, ArgusGroup]
    plans: list[ArgusReleasePlan]
    links: list[IssueLink]
    jira: dict[UUID, JiraIssue] = field(default_factory=dict)
    github: dict[UUID, GithubIssue] = field(default_factory=dict)
    first_runs: dict[UUID, UUID] = field(default_factory=dict)
    comment_counts: dict[UUID, int] = field(default_factory=dict)
    issue_counts: dict[UUID, int] = field(default_factory=dict)


def count(tests: list[TestEntry], issues: list[IssueEntry]) -> Counts:
    statuses = [entry["status"] for entry in tests]
    return Counts(
        executed=sum(status in FINAL for status in statuses),
        passed=sum(status in PASSED for status in statuses),
        failed=sum(status in FAILED for status in statuses),
        aborted=sum(status in ABORTED for status in statuses),
        in_progress=sum(status in IN_PROGRESS for status in statuses),
        pending=sum(status == PENDING for status in statuses),
        issues_new=sum(issue["novelty"] == "new" for issue in issues),
        issues_existing=sum(issue["novelty"] == "existing" for issue in issues),
        issues_fixed=sum(issue["status"] == "fixed" for issue in issues),
    )


def filter_issue(issue: IssueEntry, test_ids: set[str]) -> IssueEntry:
    """The issue as the given tests alone see it: its status, its latest-run mark, its tests, runs and links."""
    links = [link for link in issue["issue"].get("links", []) if str(link.get("test_id")) in test_ids]
    open_tests = sorted(test_ids.intersection(issue.get("open_test_ids", issue["test_ids"])))
    latest_tests = sorted(test_ids.intersection(issue.get("latest_test_ids", [])))
    return {**issue, "status": "open" if open_tests else "fixed", "on_latest_run": bool(latest_tests),
            "open_test_ids": open_tests, "latest_test_ids": latest_tests,
            "test_ids": sorted(test_ids.intersection(issue["test_ids"])),
            "run_ids": sorted({str(link["run_id"]) for link in links}) or issue["run_ids"],
            "issue": {**issue["issue"], "links": links}}


def filter_summary(summary: Summary, test_ids: set[str]) -> Summary:
    tests = [entry for entry in summary["tests"] if entry["test_id"] in test_ids]
    issues = [filter_issue(issue, test_ids) for issue in summary["issues"] if test_ids.intersection(issue["test_ids"])]
    return Summary(version=summary["version"], counts=count(tests, issues), tests=tests, issues=issues)


def latest(runs: list[SummaryRun]) -> SummaryRun:
    return max(runs, key=lambda run: (run.version.sort_key(), run.start_time))


class SummaryBuilder:
    def __init__(self, data: ReleaseData) -> None:
        self.data = data
        self.runs = [run for run in data.runs if self._counted(run.test_id)]
        self.runs_by_id = {run.id: run for run in self.runs}
        self.links_by_run: dict[UUID, list[IssueLink]] = defaultdict(list)
        for link in data.links:
            if link.run_id in self.runs_by_id:
                self.links_by_run[link.run_id].append(link)
        self.planned: dict[ScyllaVersion, set[UUID]] = defaultdict(set)
        for plan in data.plans:
            if version := parse_version(plan.target_version):
                self.planned[version].update(self._plan_tests(plan))

    def _counted(self, test_id: UUID | None) -> bool:
        test = self.data.tests.get(test_id)
        if not test or not test.enabled:
            return False
        group = self.data.groups.get(test.group_id)
        return group is None or group.enabled

    def _plan_tests(self, plan: ArgusReleasePlan) -> set[UUID]:
        planned = {test_id for test_id in plan.tests if self._counted(test_id)}
        groups = set(plan.groups)
        planned.update(test.id for test in self.data.tests.values()
                       if test.group_id in groups and self._counted(test.id))
        return planned

    def build(self) -> dict[tuple[str, str], Summary]:
        by_version: dict[ScyllaVersion, list[SummaryRun]] = defaultdict(list)
        for run in self.runs:
            by_version[run.version].append(run)
        versions = set(by_version) | set(self.planned)
        families: dict[str, list[ScyllaVersion]] = defaultdict(list)
        for version in versions:
            families[version.family].append(version)

        summaries: dict[tuple[str, str], Summary] = {}
        for family, members in families.items():
            for version in members:
                summaries[(family, str(version))] = self._version_summary(
                    version, by_version.get(version, []), self.planned.get(version, set()))
            family_runs = [run for version in members for run in by_version.get(version, [])]
            family_planned = set().union(*(self.planned.get(version, set()) for version in members))
            summaries[(family, ROLLUP_VERSION)] = self._family_summary(family, family_runs, family_planned)
        return summaries

    def _version_summary(self, version: ScyllaVersion, runs: list[SummaryRun], planned: set[UUID]) -> Summary:
        results = self._results(runs)
        tests = self._test_entries(results, planned)
        issues = self._issue_entries(runs, lambda first: first.version == version, results=None)
        return Summary(version=str(version), counts=count(tests, issues), tests=tests, issues=issues)

    def _family_summary(self, family: str, runs: list[SummaryRun], planned: set[UUID]) -> Summary:
        results = self._results(runs)
        tests = self._test_entries(results, planned)
        issues = self._issue_entries(runs, lambda first: first.version.family == family, results=results)
        return Summary(version=None, counts=count(tests, issues), tests=tests, issues=issues)

    @staticmethod
    def _results(runs: list[SummaryRun]) -> dict[UUID, SummaryRun]:
        per_test: dict[UUID, list[SummaryRun]] = defaultdict(list)
        for run in runs:
            per_test[run.test_id].append(run)
        return {test_id: latest(test_runs) for test_id, test_runs in per_test.items()}

    def _test_entry(self, test_id: UUID, run: SummaryRun | None) -> TestEntry:
        test = self.data.tests[test_id]
        group = self.data.groups.get(test.group_id)
        return TestEntry(
            test_id=str(test_id),
            group_id=str(test.group_id),
            test_name=test.pretty_name or test.name,
            group_name=(group.pretty_name or group.name) if group else "",
            status=run.status if run else PENDING,
            run_id=str(run.id) if run else None,
            build_id=run.build_id if run else None,
            build_number=run.build_number if run else None,
            version=str(run.version) if run else None,
            issues=self.data.issue_counts.get(run.id, 0) if run else 0,
            comments=self.data.comment_counts.get(run.id, 0) if run else 0,
            start_time=run.start_time.isoformat() if run and run.start_time else None,
        )

    def _test_entries(self, results: dict[UUID, SummaryRun], planned: set[UUID]) -> list[TestEntry]:
        entries = [self._test_entry(test_id, run) for test_id, run in results.items()]
        entries.extend(self._test_entry(test_id, None) for test_id in planned - set(results))
        return sorted(entries, key=lambda entry: (entry["group_name"], entry["test_name"]))

    def _issue_entries(self, runs: list[SummaryRun], is_new, results: dict[UUID, SummaryRun] | None) -> list[IssueEntry]:
        runs_by_issue: dict[UUID, list[SummaryRun]] = defaultdict(list)
        links_by_issue: dict[UUID, list[IssueLink]] = defaultdict(list)
        for run in runs:
            for link in self.links_by_run.get(run.id, []):
                runs_by_issue[link.issue_id].append(run)
                links_by_issue[link.issue_id].append(link)
        entries = []
        for issue_id, issue_runs in runs_by_issue.items():
            entry = self._describe_issue(issue_id)
            first = self._first_run(issue_id)
            test_ids = sorted({str(run.test_id) for run in issue_runs})
            if results is None:
                open_tests, latest_tests = test_ids, []
            else:
                open_tests, latest_tests = self._issue_tests(issue_id, issue_runs, results)
            tracked = issue_id in self.data.jira or issue_id in self.data.github
            entries.append(IssueEntry(
                **entry,
                novelty="new" if tracked and first is not None and is_new(first) else "existing",
                status="open" if open_tests else "fixed",
                on_latest_run=bool(latest_tests),
                open_test_ids=open_tests,
                latest_test_ids=latest_tests,
                test_ids=test_ids,
                run_ids=sorted({str(run.id) for run in issue_runs}),
                issue=self._issue_card(issue_id, links_by_issue[issue_id]),
            ))
        return sorted(entries, key=lambda entry: entry["key"])

    def _first_run(self, issue_id: UUID) -> SummaryRun | None:
        first_run_id = self.data.first_runs.get(issue_id)
        return self.runs_by_id.get(first_run_id) if first_run_id else None

    def _issue_tests(self, issue_id: UUID, issue_runs: list[SummaryRun],
                     results: dict[UUID, SummaryRun]) -> tuple[list[str], list[str]]:
        """The tests that keep the issue open in the family, and those whose latest run carries it. A test keeps
        it open until it ran again to a final status on a later version without it."""
        open_tests, latest_tests = set(), set()
        for test_id in {run.test_id for run in issue_runs}:
            result = results[test_id]
            if any(link.issue_id == issue_id for link in self.links_by_run.get(result.id, [])):
                open_tests.add(str(test_id))
                latest_tests.add(str(test_id))
                continue
            linked_versions = [run.version.sort_key() for run in issue_runs if run.test_id == test_id]
            if result.status not in FINAL or result.version.sort_key() <= max(linked_versions):
                open_tests.add(str(test_id))
        return sorted(open_tests), sorted(latest_tests)

    def _issue_card(self, issue_id: UUID, links: list[IssueLink]) -> dict:
        dumped_links = [link.model_dump(mode="json") for link in links]
        tracker = self.data.jira.get(issue_id) or self.data.github.get(issue_id)
        if tracker is not None:
            return {**tracker_card(tracker), "links": dumped_links}
        return {"id": str(issue_id), "subtype": "unknown", "links": dumped_links}

    def _describe_issue(self, issue_id: UUID) -> dict:
        tracker = self.data.jira.get(issue_id) or self.data.github.get(issue_id)
        if tracker is not None:
            return {"id": str(issue_id), **tracker_fields(tracker)}
        link_type = next((link.type for link in self.data.links if link.issue_id == issue_id), None)
        return {"id": str(issue_id), "type": "github" if link_type in ("github", "issues") else "jira",
                "key": str(issue_id), "title": None, "url": None, "state": None}


def build_summaries(data: ReleaseData) -> dict[tuple[str, str], Summary]:
    return SummaryBuilder(data).build()


def family_sort_key(family: str) -> tuple:
    version = parse_version(family)
    return version.sort_key() if version else ((), 0)


def version_sort_key(version: str) -> tuple:
    parsed = parse_version(version)
    return parsed.sort_key() if parsed else ((), 0)


def version_pattern(regex: str | None) -> re.Pattern | None:
    if not regex:
        return None
    try:
        return re.compile(regex)
    except re.error:
        LOGGER.warning("Ignoring the invalid version regex %r", regex)
        return None


def as_utc(moment: datetime | None) -> datetime | None:
    if moment is None or moment.tzinfo:
        return moment
    return moment.replace(tzinfo=UTC)


def first_link(links: list[IssueLink]) -> IssueLink:
    return min(links, key=lambda link: as_utc(link.added_on) or LAST)


def tracker_fields(issue: JiraIssue | GithubIssue) -> dict:
    """What a summary shows of an issue from its tracker; read again on every response."""
    if isinstance(issue, JiraIssue):
        return {"type": "jira", "key": issue.key, "title": issue.summary, "url": issue.permalink, "state": issue.state}
    return {"type": "github", "key": f"{issue.owner}/{issue.repo}#{issue.number}", "title": issue.title,
            "url": issue.url, "state": issue.state}


def tracker_card(issue: JiraIssue | GithubIssue) -> dict:
    return {**issue.model_dump(mode="json"), "subtype": "jira" if isinstance(issue, JiraIssue) else "github"}


async def refresh_trackers(summaries: dict[tuple[str, str], Summary]) -> dict[tuple[str, str], Summary]:
    """The summaries with each issue's tracker state, title and card as the trackers have them now, so an issue
    closed after the summary was computed shows as closed."""
    issue_ids = list({UUID(issue["id"]) for summary in summaries.values() for issue in summary["issues"]})
    trackers: dict[str, JiraIssue | GithubIssue] = {}
    for batch in chunk(issue_ids):
        jira, github = await asyncio.gather(JiraIssue.find(id__in=batch).all(), GithubIssue.find(id__in=batch).all())
        trackers.update({str(issue.id): issue for issue in [*jira, *github]})
    if not trackers:
        return summaries

    def refreshed(issue: IssueEntry) -> IssueEntry:
        tracker = trackers.get(issue["id"])
        if tracker is None:
            return issue
        return {**issue, **tracker_fields(tracker),
                "issue": {**tracker_card(tracker), "links": issue["issue"].get("links", [])}}

    return {key: {**summary, "issues": [refreshed(issue) for issue in summary["issues"]]}
            for key, summary in summaries.items()}


def _log_failure(task: asyncio.Task) -> None:
    if not task.cancelled() and (exception := task.exception()) is not None:
        LOGGER.error("The background recompute of a release summary failed", exc_info=exception)


class ReleaseSummaryService:
    _recomputes: dict[UUID, tuple[asyncio.Task, datetime]] = {}

    async def get(self, release_id: UUID, test_ids: set[UUID] | None = None, wait: bool = False) -> dict:
        """The release's summary. A stale one with stored rows comes back at once, marked stale, while a
        recompute runs in the background; ``wait`` waits for that recompute instead."""
        try:
            release = await ArgusRelease.get(id=release_id)
        except DocumentNotFound as exception:
            raise ReleaseSummaryException(f"Release {release_id} does not exist") from exception

        stored, invalidated_at, generated_at = await self._read(release_id)
        stale = generated_at is None or (invalidated_at is not None and invalidated_at >= generated_at)
        summaries = stored
        if stale and stored and not wait:
            self._recompute_task(release, invalidated_at)
        elif stale:
            try:
                summaries, generated_at = await asyncio.shield(self._recompute_task(release, invalidated_at))
                stale = False
            except (DriverException, NoHostAvailable):
                LOGGER.exception("Failed to recompute the release summary of %s", release_id)
                if not stored:
                    raise
        return self._response(release, await refresh_trackers(summaries), generated_at, stale, test_ids)

    async def get_for_view(self, view_id: UUID, wait: bool = False) -> dict:
        tests = await UserViewService().resolve_view_tests(view_id)
        by_release: dict[UUID, set[UUID]] = defaultdict(set)
        for test in tests:
            if test.release_id:
                by_release[test.release_id].add(test.id)
        releases = [await self.get(release_id, test_ids, wait=wait) for release_id, test_ids in by_release.items()]
        return {"releases": sorted(releases, key=lambda release: release["release_name"])}

    @staticmethod
    async def _read(release_id: UUID) -> tuple[dict[tuple[str, str], Summary], datetime | None, datetime | None]:
        rows = await select_rows(ReleaseSummary.find(release_id=release_id),
                                 "family", "version", "invalidated_at", "generated_at", "payload")
        if not rows:
            return {}, None, None
        summaries = {(row["family"], row["version"]): json.loads(row["payload"])
                     for row in rows if row["family"] is not None and row["payload"]}
        return summaries, as_utc(rows[0]["invalidated_at"]), as_utc(rows[0]["generated_at"])

    def _recompute_task(self, release: ArgusRelease, invalidated_at: datetime | None) -> asyncio.Task:
        """Share a running recompute of the release, unless it started before the change that made the summary
        stale; then start one that sees the change."""
        release_id = release.id
        running = self._recomputes.get(release_id)
        if running is None or running[0].done() or (invalidated_at is not None and running[1] <= invalidated_at):
            now = datetime.now(UTC)
            started_at = now.replace(microsecond=now.microsecond // 1000 * 1000)
            task = asyncio.create_task(self._recompute(release, started_at))
            self._recomputes[release_id] = (task, started_at)
            task.add_done_callback(lambda done: self._recomputes.pop(release_id, None)
                                   if self._recomputes.get(release_id, (None,))[0] is done else None)
            task.add_done_callback(_log_failure)
            running = (task, started_at)
        return running[0]

    async def _recompute(self, release: ArgusRelease,
                         started_at: datetime) -> tuple[dict[tuple[str, str], Summary], datetime]:
        summaries = await asyncio.to_thread(build_summaries, await self._load(release))
        try:
            await self._write(release.id, summaries, started_at)
        except (DriverException, NoHostAvailable):
            LOGGER.warning("Failed to store the release summary of %s", release.id, exc_info=True)
        return summaries, started_at

    @staticmethod
    async def _write(release_id: UUID, summaries: dict[tuple[str, str], Summary], started_at: datetime) -> None:
        existing = await select_rows(ReleaseSummary.find(release_id=release_id), "family", "version")
        gone = {(row["family"], row["version"]) for row in existing if row["family"] is not None} - set(summaries)
        await asyncio.gather(*(
            ReleaseSummary.find(release_id=release_id, family=family, version=version).update(
                payload=json.dumps(summary))
            for (family, version), summary in summaries.items()
        ))
        await asyncio.gather(*(
            ReleaseSummary.find(release_id=release_id, family=family, version=version).delete()
            for family, version in gone
        ))
        await ReleaseSummary.find(release_id=release_id).update(generated_at=started_at)

    @staticmethod
    async def _load(release: ArgusRelease) -> ReleaseData:
        release_id = release.id
        pattern = version_pattern(release.valid_version_regex)
        run_rows, tests, groups, plans, links, comment_rows = await asyncio.gather(
            asyncio.gather(*(model.get_summary_rows_for_release(release_id) for model in all_plugin_models())),
            ArgusTest.find(release_id=release_id).all(),
            ArgusGroup.find(release_id=release_id).all(),
            ArgusReleasePlan.find(release_id=release_id).all(),
            IssueLink.find(release_id=release_id).all(),
            select_rows(ArgusTestRunComment.find(release_id=release_id), "test_run_id"),
        )
        runs = []
        for row in (row for rows in run_rows for row in rows):
            version = parse_version(row["scylla_version"])
            if version is None or row["test_id"] is None:
                continue
            if pattern and not pattern.search(row["scylla_version"]):
                continue
            runs.append(SummaryRun(id=row["id"], test_id=row["test_id"], build_id=row["build_id"],
                                   build_number=row["build_number"], status=row["status"],
                                   start_time=as_utc(row["start_time"]), version=version))
        data = ReleaseData(runs=runs, tests={test.id: test for test in tests},
                           groups={group.id: group for group in groups}, links=list(links),
                           plans=[plan for plan in plans
                                  if not pattern or (plan.target_version and pattern.search(plan.target_version))])
        data.comment_counts = dict(Counter(row["test_run_id"] for row in comment_rows))
        issues_by_run: dict[UUID, set[UUID]] = defaultdict(set)
        for link in links:
            issues_by_run[link.run_id].add(link.issue_id)
        data.issue_counts = {run_id: len(issue_ids) for run_id, issue_ids in issues_by_run.items()}
        issue_ids = list({link.issue_id for link in links})
        issue_links = await gather_limited((IssueLink.find(issue_id=issue_id).all() for issue_id in issue_ids),
                                           limit=FIRST_LINK_READS)
        data.first_runs = {issue_id: first_link(found).run_id
                           for issue_id, found in zip(issue_ids, issue_links) if found}
        for batch in chunk(issue_ids):
            jira, github = await asyncio.gather(JiraIssue.find(id__in=batch).all(),
                                                GithubIssue.find(id__in=batch).all())
            data.jira.update({issue.id: issue for issue in jira})
            data.github.update({issue.id: issue for issue in github})
        return data

    @staticmethod
    def _response(release: ArgusRelease, summaries: dict[tuple[str, str], Summary], generated_at: datetime | None,
                  stale: bool, test_ids: set[UUID] | None) -> dict:
        wanted = {str(test_id) for test_id in test_ids} if test_ids is not None else None
        families: dict[str, dict] = {}
        for (family, version), summary in summaries.items():
            if wanted is not None:
                summary = filter_summary(summary, wanted)
            entry = families.setdefault(family, {"family": family, "rollup": None, "versions": []})
            if version == ROLLUP_VERSION:
                entry["rollup"] = summary
            else:
                entry["versions"].append(summary)
        for entry in families.values():
            entry["versions"].sort(key=lambda summary: version_sort_key(summary["version"]))
        families = {family: entry for family, entry in families.items()
                    if entry["rollup"] and (wanted is None or entry["rollup"]["tests"])}
        return {
            "release_id": str(release.id),
            "release_name": release.name,
            "generated_at": generated_at.isoformat() if generated_at else None,
            "stale": stale,
            "families": sorted(families.values(), key=lambda entry: family_sort_key(entry["family"]), reverse=True),
        }
