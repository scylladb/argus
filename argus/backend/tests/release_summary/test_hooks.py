from uuid import UUID

import pytest

from argus.backend.service.release_summary import ReleaseSummaryService
from argus.backend.tests.release_summary.helpers import (
    SCT,
    by_version,
    link_jira,
    mocked_issue_service,
    new_jira_key,
    seed_release,
    submit_run,
    unique,
)
from argus.common.enums import TestStatus

pytestmark = pytest.mark.docker_required


async def read(release_id: UUID) -> dict:
    return await ReleaseSummaryService().get(release_id)


def status_of(summary: dict, family: str, version: str | None, test_name: str) -> str | None:
    if not any(entry["family"] == family for entry in summary["families"]):
        return None
    rows = by_version(summary, family)
    if version not in rows:
        return None
    return next((entry["status"] for entry in rows[version]["tests"] if entry["test_name"] == test_name), None)


async def test_a_client_status_update_shows_on_the_next_read(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    test = seeded.tests[0]
    run_id = await submit_run(client_service, test, "2031.1.0", "running")
    assert status_of(await read(seeded.release.id), "2031.1.0", "2031.1.0", test.name) == "running"

    await client_service.update_run_status(SCT, run_id, "failed")

    assert status_of(await read(seeded.release.id), "2031.1.0", "2031.1.0", test.name) == "failed"


async def test_a_status_change_from_the_ui_shows_on_the_next_read(release_manager_service, client_service,
                                                                  testrun_service, logged_in_user):
    seeded = await seed_release(release_manager_service, test_count=1)
    test = seeded.tests[0]
    run_id = await submit_run(client_service, test, "2031.2.0", "failed")
    await read(seeded.release.id)

    await testrun_service.change_run_status(test.id, run_id, TestStatus.PASSED, logged_in_user)

    assert status_of(await read(seeded.release.id), "2031.2.0", "2031.2.0", test.name) == "passed"


async def test_a_product_version_submit_moves_the_run_to_its_version(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    test = seeded.tests[0]
    run_id = await submit_run(client_service, test, None, "passed")
    assert (await read(seeded.release.id))["families"] == []

    await client_service.submit_product_version(SCT, run_id, "2031.3.0~rc0")

    assert status_of(await read(seeded.release.id), "2031.3.0", "2031.3.0~rc0", test.name) == "passed"


async def test_a_target_package_submit_moves_the_run_to_its_version(release_manager_service, client_service,
                                                                    sct_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    test = seeded.tests[0]
    run_id = await submit_run(client_service, test, None, "passed")
    await read(seeded.release.id)

    await sct_service.submit_packages(run_id, [{"name": "scylla-server-target", "version": "2031.4.0~rc1",
                                                "date": "20310101", "revision_id": "abc", "build_id": "def"}])

    assert status_of(await read(seeded.release.id), "2031.4.0", "2031.4.0~rc1", test.name) == "passed"


async def test_moving_a_test_to_another_group_shows_on_the_next_read(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=1)
    test = seeded.tests[0]
    await submit_run(client_service, test, "2031.5.0", "passed")
    await read(seeded.release.id)
    new_group = await release_manager_service.create_group(
        unique("group"), "Moved", build_system_id=seeded.release.name, release_id=seeded.release.id)

    await release_manager_service.batch_move_tests(new_group.id, [test.id])

    [entry] = by_version(await read(seeded.release.id), "2031.5.0")["2031.5.0"]["tests"]
    assert entry["group_id"] == str(new_group.id)
    assert entry["group_name"] == "Moved"


async def test_linking_and_unlinking_an_issue_changes_the_issue_counts(release_manager_service, client_service,
                                                                       logged_in_user):
    seeded = await seed_release(release_manager_service, test_count=1)
    test = seeded.tests[0]
    run_id = await submit_run(client_service, test, "2031.6.0", "failed")
    issues = mocked_issue_service()
    await read(seeded.release.id)

    linked = await link_jira(issues, new_jira_key(), test, run_id, logged_in_user)
    after_link = by_version(await read(seeded.release.id), "2031.6.0")["2031.6.0"]
    await issues.delete(issue_id=UUID(str(linked["id"])), run_id=run_id, user=logged_in_user)
    after_unlink = by_version(await read(seeded.release.id), "2031.6.0")["2031.6.0"]

    assert after_link["counts"]["issues_new"] == 1
    assert after_unlink["counts"]["issues_new"] == 0
    assert after_unlink["issues"] == []


async def test_a_comment_marks_the_summary_stale(release_manager_service, client_service, testrun_service,
                                                 logged_in_user):
    seeded = await seed_release(release_manager_service, test_count=1)
    test = seeded.tests[0]
    run_id = await submit_run(client_service, test, "2031.7.0", "failed")
    before = await read(seeded.release.id)

    await testrun_service.post_run_comment(test.id, run_id, "looking", {}, [], logged_in_user)

    assert (await read(seeded.release.id))["generated_at"] > before["generated_at"]
