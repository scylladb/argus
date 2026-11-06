import asyncio
import time
from unittest.mock import patch

import pytest

from argus.backend.models.release_summary import mark_release_summary_stale
from argus.backend.service.release_summary import ReleaseSummaryService
from argus.backend.tests.release_summary.helpers import (
    by_version,
    create_plan,
    fake_remote_jira_issue,
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
    latest = {issue["key"]: issue["on_latest_run"] for issue in rows[None]["issues"]}
    assert latest == {old_key: False, fixed_key: False, open_key: True}
    assert not any(issue["on_latest_run"] for issue in rows["2030.6.0~rc1"]["issues"])


async def test_the_tracker_state_is_read_on_every_response(release_manager_service, client_service, logged_in_user):
    seeded = await seed_release(release_manager_service, test_count=1)
    issues = mocked_issue_service()
    key = new_jira_key()
    run = await submit_run(client_service, seeded.tests[0], "2030.7.0", "failed")
    await link_jira(issues, key, seeded.tests[0], run, logged_in_user)
    before = by_version(await ReleaseSummaryService().get(seeded.release.id), "2030.7.0")[None]["issues"][0]
    closed = fake_remote_jira_issue(key)
    closed.fields.status.name = "Closed"
    closed.fields.summary = "Renamed in Jira"
    issues.jira.jira.search_issues.return_value = [closed]

    await issues.jira.refresh_stale_issues()
    after = by_version(await ReleaseSummaryService().get(seeded.release.id), "2030.7.0")[None]["issues"][0]

    assert (before["state"], before["title"]) == ("open", f"Issue {key}")
    assert (after["state"], after["title"]) == ("closed", "Renamed in Jira")
    assert after["issue"]["state"] == "closed" and after["issue"]["links"] == before["issue"]["links"]


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


async def test_a_view_sees_an_issue_through_its_own_tests(release_manager_service, client_service,
                                                         logged_in_user):
    seeded = await seed_release(release_manager_service, test_count=2)
    fixed_test, open_test = seeded.tests
    issues = mocked_issue_service()
    key = new_jira_key()
    fixed_run = await submit_run(client_service, fixed_test, "2030.12.0~rc1", "failed")
    await link_jira(issues, key, fixed_test, fixed_run, logged_in_user)
    await submit_run(client_service, fixed_test, "2030.12.0~rc2", "passed")
    open_run = await submit_run(client_service, open_test, "2030.12.0~rc2", "failed")
    await link_jira(issues, key, open_test, open_run, logged_in_user)

    whole = by_version(await ReleaseSummaryService().get(seeded.release.id, wait=True), "2030.12.0")[None]
    seen = by_version(await ReleaseSummaryService().get(seeded.release.id, test_ids={fixed_test.id}),
                      "2030.12.0")[None]

    [whole_issue], [seen_issue] = whole["issues"], seen["issues"]
    assert (whole_issue["status"], whole_issue["on_latest_run"]) == ("open", True)
    assert (seen_issue["status"], seen_issue["on_latest_run"]) == ("fixed", False)
    assert seen_issue["test_ids"] == [str(fixed_test.id)] and seen_issue["run_ids"] == [str(fixed_run)]
    assert {link["run_id"] for link in seen_issue["issue"]["links"]} == {str(fixed_run)}
    assert seen["counts"]["issues_fixed"] == 1


async def test_deleting_a_release_deletes_its_summary(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    await submit_run(client_service, seeded.tests[0], "2030.14.0", "passed")
    await ReleaseSummaryService().get(seeded.release.id)

    await release_manager_service.delete_release(seeded.release.id)

    assert await ReleaseSummaryService._read(seeded.release.id) == ({}, None, None)


async def test_a_failed_mark_does_not_fail_the_write_that_caused_it(release_manager_service):
    seeded = await seed_release(release_manager_service, test_count=1)

    with patch("argus.backend.models.release_summary.ReleaseSummary.find", side_effect=RuntimeError("boom")):
        await mark_release_summary_stale(seeded.release.id)


async def test_a_fresh_summary_is_not_recomputed_and_a_mark_recomputes_it(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    await submit_run(client_service, seeded.tests[0], "2030.8.0", "passed")
    service = ReleaseSummaryService()

    first = await service.get(seeded.release.id)
    second = await service.get(seeded.release.id)
    await mark_release_summary_stale(seeded.release.id)
    third = await service.get(seeded.release.id, wait=True)

    assert second["generated_at"] == first["generated_at"]
    assert third["generated_at"] > first["generated_at"]


async def test_a_stale_summary_is_served_at_once_and_refreshed_in_the_background(release_manager_service,
                                                                                 client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    await submit_run(client_service, seeded.tests[0], "2030.8.0", "passed")
    service = ReleaseSummaryService()
    first = await service.get(seeded.release.id)
    await submit_run(client_service, seeded.tests[0], "2030.8.1", "failed")

    served = await service.get(seeded.release.id)
    running = ReleaseSummaryService._recomputes[seeded.release.id][0]
    await running
    refreshed = await service.get(seeded.release.id)

    assert served["stale"] is True and served["generated_at"] == first["generated_at"]
    assert "2030.8.1" not in {family["family"] for family in served["families"]}
    assert refreshed["stale"] is False and "2030.8.1" in {family["family"] for family in refreshed["families"]}


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
    recomputed = await service.get(seeded.release.id, wait=True)
    settled = await service.get(seeded.release.id)

    assert recomputed["generated_at"] > raced["generated_at"]
    assert settled["generated_at"] == recomputed["generated_at"]


async def test_a_read_after_a_mark_does_not_join_an_older_recompute(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    await submit_run(client_service, seeded.tests[0], "2030.9.0", "passed")
    service = ReleaseSummaryService()
    load = ReleaseSummaryService._load
    loading, release_load = asyncio.Event(), asyncio.Event()

    async def slow_load(release):
        data = await load(release)
        loading.set()
        await release_load.wait()
        return data

    with patch.object(ReleaseSummaryService, "_load", side_effect=slow_load):
        first = asyncio.create_task(service.get(seeded.release.id))
        await loading.wait()
        await submit_run(client_service, seeded.tests[0], "2030.9.1", "failed")
        await mark_release_summary_stale(seeded.release.id)
        second = asyncio.create_task(service.get(seeded.release.id))
        await asyncio.sleep(0.2)
        release_load.set()
        early, late = await first, await second

    assert "2030.9.1" not in {version["version"] for family in early["families"] for version in family["versions"]}
    assert "2030.9.1" in {version["version"] for family in late["families"] for version in family["versions"]}


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
    assert [entry["family"] for entry in (await ReleaseSummaryService().get(seeded.release.id, wait=True))[
        "families"]] == ["2030.11.0", "2029.5.0"]


async def test_an_invalid_regex_filters_nothing(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    await edit_regex(release_manager_service, seeded.release, "2030.12(")
    await submit_run(client_service, seeded.tests[0], "2029.6.0", "passed")

    summary = await ReleaseSummaryService().get(seeded.release.id)

    assert [entry["family"] for entry in summary["families"]] == ["2029.6.0"]


async def test_each_issue_carries_the_issue_and_its_links_in_scope(release_manager_service, client_service,
                                                                   logged_in_user):
    seeded = await seed_release(release_manager_service, test_count=1)
    test = seeded.tests[0]
    issues = mocked_issue_service()
    key = new_jira_key()
    rc1 = await submit_run(client_service, test, "2030.14.0~rc1", "failed")
    rc2 = await submit_run(client_service, test, "2030.14.0~rc2", "failed")
    await link_jira(issues, key, test, rc1, logged_in_user)
    await link_jira(issues, key, test, rc2, logged_in_user)

    rows = by_version(await ReleaseSummaryService().get(seeded.release.id), "2030.14.0")

    [rc1_issue] = rows["2030.14.0~rc1"]["issues"]
    [family_issue] = rows[None]["issues"]
    assert rc1_issue["issue"]["subtype"] == "jira"
    assert rc1_issue["issue"]["key"] == key
    assert rc1_issue["issue"]["permalink"].endswith(f"/browse/{key}")
    assert [link["run_id"] for link in rc1_issue["issue"]["links"]] == [str(rc1)]
    assert sorted(link["run_id"] for link in family_issue["issue"]["links"]) == sorted([str(rc1), str(rc2)])
    assert family_issue["issue"]["links"][0]["user_id"] == str(logged_in_user.id)


async def test_each_test_counts_the_issues_and_comments_of_its_run(release_manager_service, client_service,
                                                                  testrun_service, logged_in_user, asgi_app):
    seeded = await seed_release(release_manager_service, test_count=2)
    discussed, quiet = seeded.tests
    issues = mocked_issue_service()
    old_run = await submit_run(client_service, discussed, "2031.1.0~rc1", "failed")
    await testrun_service.post_run_comment(discussed.id, old_run, "an older run", {}, [], logged_in_user)
    run = await submit_run(client_service, discussed, "2031.1.0~rc2", "failed")
    await link_jira(issues, new_jira_key(), discussed, run, logged_in_user)
    await link_jira(issues, new_jira_key() + "1", discussed, run, logged_in_user)
    for message in ("OOM again", "same as last week"):
        await testrun_service.post_run_comment(discussed.id, run, message, {}, [], logged_in_user)
    await submit_run(client_service, quiet, "2031.1.0~rc2", "passed")

    rows = by_version(await ReleaseSummaryService().get(seeded.release.id), "2031.1.0")

    entries = {entry["test_id"]: entry for entry in rows["2031.1.0~rc2"]["tests"]}
    assert (entries[str(discussed.id)]["issues"], entries[str(discussed.id)]["comments"]) == (2, 2)
    assert (entries[str(quiet.id)]["issues"], entries[str(quiet.id)]["comments"]) == (0, 0)
    older = {entry["test_id"]: entry for entry in rows["2031.1.0~rc1"]["tests"]}
    assert (older[str(discussed.id)]["issues"], older[str(discussed.id)]["comments"]) == (0, 1)
