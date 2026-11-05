import time
from unittest.mock import patch

import pytest

from argus.backend.models.release_summary import mark_release_summary_stale
from argus.backend.service.release_summary import ReleaseSummaryService
from argus.backend.tests.release_summary.helpers import (
    by_version,
    create_plan,
    link_github,
    link_jira,
    mocked_issue_service,
    new_jira_key,
    seed_release,
    submit_run,
)

pytestmark = pytest.mark.docker_required


def statuses(summary: dict) -> dict[str, str]:
    return {entry["test_name"]: entry["status"] for entry in summary["tests"]}


def issue_states(summary: dict) -> dict[str, tuple[str, str]]:
    return {issue["key"]: (issue["novelty"], issue["status"]) for issue in summary["issues"]}


async def test_versions_and_the_family_rollup_count_each_test(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=3)
    first, second, third = seeded.tests
    await submit_run(client_service, first, "2030.1.0~rc0", "failed")
    await submit_run(client_service, first, "2030.1.0~rc1", "passed")
    await submit_run(client_service, second, "2030.1.0~rc1", "aborted")
    await submit_run(client_service, second, "2030.1.0", "running")
    await submit_run(client_service, third, "2030.1.0.0.20300101.abcdef", "test_error")

    summary = await ReleaseSummaryService().get(seeded.release.id)

    assert [entry["family"] for entry in summary["families"]] == ["2030.1.0"]
    rows = by_version(summary, "2030.1.0")
    assert list(rows) == ["2030.1.0~rc0", "2030.1.0~rc1", "2030.1.0", None]
    assert rows["2030.1.0~rc0"]["counts"] | {} == {
        "executed": 1, "passed": 0, "failed": 1, "aborted": 0, "in_progress": 0, "pending": 0,
        "issues_new": 0, "issues_existing": 0, "issues_fixed": 0}
    assert rows["2030.1.0~rc1"]["counts"]["executed"] == 2
    assert rows["2030.1.0~rc1"]["counts"]["aborted"] == 1
    assert rows["2030.1.0"]["counts"]["in_progress"] == 1
    assert rows["2030.1.0"]["counts"]["failed"] == 1
    assert statuses(rows[None]) == {first.name: "passed", second.name: "running", third.name: "test_error"}
    assert rows[None]["counts"]["executed"] == 2


async def test_a_test_counts_by_its_latest_run_on_the_version(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    test = seeded.tests[0]
    await submit_run(client_service, test, "2030.2.0~rc0", "failed")
    await submit_run(client_service, test, "2030.2.0~rc0", "passed")

    rows = by_version(await ReleaseSummaryService().get(seeded.release.id), "2030.2.0")

    assert rows["2030.2.0~rc0"]["counts"]["passed"] == 1
    assert rows["2030.2.0~rc0"]["counts"]["failed"] == 0


async def test_a_disabled_test_and_an_unparsed_version_are_left_out(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=2)
    enabled, disabled = seeded.tests
    await submit_run(client_service, enabled, "2030.3.0", "passed")
    await submit_run(client_service, enabled, "master", "failed")
    await submit_run(client_service, disabled, "2030.3.0", "failed")
    await release_manager_service.toggle_test_enabled(disabled.id, False)

    summary = await ReleaseSummaryService().get(seeded.release.id)

    assert [entry["family"] for entry in summary["families"]] == ["2030.3.0"]
    assert statuses(by_version(summary, "2030.3.0")["2030.3.0"]) == {enabled.name: "passed"}


async def test_planned_tests_without_a_run_are_pending(release_manager_service, client_service, logged_in_user):
    seeded = await seed_release(release_manager_service, test_count=3)
    ran_on_rc1, ran_on_rc0, never_ran = seeded.tests
    await create_plan(seeded.release, [ran_on_rc1, ran_on_rc0, never_ran], "2030.4.0~rc1", logged_in_user)
    await submit_run(client_service, ran_on_rc1, "2030.4.0~rc1", "passed")
    await submit_run(client_service, ran_on_rc0, "2030.4.0~rc0", "passed")

    rows = by_version(await ReleaseSummaryService().get(seeded.release.id), "2030.4.0")

    assert statuses(rows["2030.4.0~rc1"]) == {
        ran_on_rc1.name: "passed", ran_on_rc0.name: "pending", never_ran.name: "pending"}
    assert rows["2030.4.0~rc1"]["counts"]["pending"] == 2
    assert statuses(rows[None])[never_ran.name] == "pending"
    assert rows[None]["counts"]["pending"] == 1


async def test_a_planned_group_and_a_planned_version_without_runs(release_manager_service, logged_in_user):
    seeded = await seed_release(release_manager_service, test_count=2)
    await create_plan(seeded.release, [], "2030.5.1", logged_in_user, groups=[seeded.group])

    rows = by_version(await ReleaseSummaryService().get(seeded.release.id), "2030.5.1")

    assert rows["2030.5.1"]["counts"]["pending"] == 2
    assert rows[None]["counts"]["pending"] == 2


async def test_issue_novelty_and_the_fixed_state(release_manager_service, client_service, logged_in_user):
    seeded = await seed_release(release_manager_service, test_count=2)
    fixed_test, still_open_test = seeded.tests
    issues = mocked_issue_service()
    old_key, fixed_key, open_key = new_jira_key(), new_jira_key() + "1", new_jira_key() + "2"

    old_run = await submit_run(client_service, fixed_test, "2030.5.0", "failed")
    await link_jira(issues, old_key, fixed_test, old_run, logged_in_user)

    rc1 = await submit_run(client_service, fixed_test, "2030.6.0~rc1", "failed")
    await link_jira(issues, fixed_key, fixed_test, rc1, logged_in_user)
    await link_jira(issues, old_key, fixed_test, rc1, logged_in_user)
    await submit_run(client_service, fixed_test, "2030.6.0~rc2", "passed")

    open_rc1 = await submit_run(client_service, still_open_test, "2030.6.0~rc1", "failed")
    await link_jira(issues, open_key, still_open_test, open_rc1, logged_in_user)
    open_rc2 = await submit_run(client_service, still_open_test, "2030.6.0~rc2", "failed")
    await link_jira(issues, open_key, still_open_test, open_rc2, logged_in_user)

    rows = by_version(await ReleaseSummaryService().get(seeded.release.id), "2030.6.0")

    assert issue_states(rows["2030.6.0~rc1"]) == {
        old_key: ("existing", "open"), fixed_key: ("new", "open"), open_key: ("new", "open")}
    assert issue_states(rows["2030.6.0~rc2"]) == {open_key: ("existing", "open")}
    assert issue_states(rows[None]) == {
        old_key: ("existing", "fixed"), fixed_key: ("new", "fixed"), open_key: ("new", "open")}
    assert rows[None]["counts"]["issues_fixed"] == 2
    assert rows[None]["counts"]["issues_new"] == 2
    assert rows[None]["counts"]["issues_existing"] == 1


async def test_a_github_issue_follows_the_same_rule(release_manager_service, client_service, logged_in_user):
    seeded = await seed_release(release_manager_service, test_count=1)
    test = seeded.tests[0]
    issues = mocked_issue_service()
    number = int(time.time_ns() % 10**6)
    key = f"scylladb/summary-repo#{number}"
    rc1 = await submit_run(client_service, test, "2030.13.0~rc1", "failed")
    await link_github(issues, number, test, rc1, logged_in_user)
    rc2 = await submit_run(client_service, test, "2030.13.0~rc2", "failed")
    await link_github(issues, number, test, rc2, logged_in_user)

    rows = by_version(await ReleaseSummaryService().get(seeded.release.id), "2030.13.0")

    assert issue_states(rows["2030.13.0~rc1"]) == {key: ("new", "open")}
    assert issue_states(rows["2030.13.0~rc2"]) == {key: ("existing", "open")}
    assert issue_states(rows[None]) == {key: ("new", "open")}


async def test_test_ids_keep_only_those_tests_and_their_issues(release_manager_service, client_service,
                                                               logged_in_user):
    seeded = await seed_release(release_manager_service, test_count=2)
    kept, dropped = seeded.tests
    issues = mocked_issue_service()
    await submit_run(client_service, kept, "2030.7.0", "passed")
    dropped_run = await submit_run(client_service, dropped, "2030.7.0", "failed")
    await link_jira(issues, new_jira_key(), dropped, dropped_run, logged_in_user)

    rows = by_version(await ReleaseSummaryService().get(seeded.release.id, test_ids={kept.id}), "2030.7.0")

    assert statuses(rows["2030.7.0"]) == {kept.name: "passed"}
    assert rows["2030.7.0"]["counts"]["failed"] == 0
    assert rows["2030.7.0"]["issues"] == []


async def test_a_fresh_summary_is_not_recomputed_and_a_mark_recomputes_it(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    await submit_run(client_service, seeded.tests[0], "2030.8.0", "passed")
    service = ReleaseSummaryService()

    first = await service.get(seeded.release.id)
    second = await service.get(seeded.release.id)
    await mark_release_summary_stale(seeded.release.id)
    third = await service.get(seeded.release.id)

    assert second["generated_at"] == first["generated_at"]
    assert third["generated_at"] > first["generated_at"]


async def test_a_mark_during_a_recompute_keeps_the_summary_stale(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    await submit_run(client_service, seeded.tests[0], "2030.9.0", "passed")
    service = ReleaseSummaryService()
    load = ReleaseSummaryService._load

    async def load_then_mark(release):
        data = await load(release)
        await mark_release_summary_stale(release.id)
        return data

    with patch.object(ReleaseSummaryService, "_load", side_effect=load_then_mark):
        raced = await service.get(seeded.release.id)
    recomputed = await service.get(seeded.release.id)
    settled = await service.get(seeded.release.id)

    assert recomputed["generated_at"] > raced["generated_at"]
    assert settled["generated_at"] == recomputed["generated_at"]


async def edit_regex(release_manager_service, release, regex: str | None) -> None:
    await release_manager_service.edit_release({
        "id": release.id, "pretty_name": release.pretty_name, "description": release.description or "",
        "valid_version_regex": regex, "enabled": True, "perpetual": False, "dormant": False, "priority": 0,
    })


async def test_the_valid_version_regex_leaves_out_other_versions(release_manager_service, client_service,
                                                                 logged_in_user):
    seeded = await seed_release(release_manager_service, test_count=2)
    own, foreign = seeded.tests
    await edit_regex(release_manager_service, seeded.release, "2030.10(.*)")
    await submit_run(client_service, own, "2030.10.0~rc0", "passed")
    await submit_run(client_service, foreign, "2029.4.2", "failed")
    await create_plan(seeded.release, [foreign], "2031.1.0", logged_in_user)

    summary = await ReleaseSummaryService().get(seeded.release.id)

    assert [entry["family"] for entry in summary["families"]] == ["2030.10.0"]


async def test_a_regex_change_shows_on_the_next_read(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=2)
    own, foreign = seeded.tests
    await submit_run(client_service, own, "2030.11.0", "passed")
    await submit_run(client_service, foreign, "2029.5.0", "failed")
    await edit_regex(release_manager_service, seeded.release, "2030.11(.*)")
    filtered = await ReleaseSummaryService().get(seeded.release.id)

    await edit_regex(release_manager_service, seeded.release, None)

    assert [entry["family"] for entry in filtered["families"]] == ["2030.11.0"]
    assert [entry["family"] for entry in (await ReleaseSummaryService().get(seeded.release.id))["families"]] == [
        "2030.11.0", "2029.5.0"]


async def test_an_invalid_regex_filters_nothing(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    await edit_regex(release_manager_service, seeded.release, "2030.12(")
    await submit_run(client_service, seeded.tests[0], "2029.6.0", "passed")

    summary = await ReleaseSummaryService().get(seeded.release.id)

    assert [entry["family"] for entry in summary["families"]] == ["2029.6.0"]
