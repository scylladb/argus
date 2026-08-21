"""Controller-level integration tests for argus/backend/controller/testrun_api.py.

This file complements the existing `test_testrun_service.py` (which focuses on
GET /test/<test_id>/runs paging/filtering).  It covers the remaining endpoints
that do NOT require external service mocking.

Out-of-scope for this iteration (deferred — needs Jenkins/Github/Jira/S3 mocks):
- /tests/<plugin>/<run_id>/log/<log_name>/download (S3)
- /tests/<plugin>/<run_id>/screenshot/<image_name>  (S3)
- /test/<test_id>/run/<run_id>/issues/...           (Github/Jira)
- /issues/get, /issues/delete                        (Github/Jira)
- /jenkins/...                                       (Jenkins)
- /terminate_stuck_runs                              (mutates ScyllaCluster session/state)
"""

import json
import time
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from coodie.exceptions import DocumentNotFound

from argus.backend.models.web import ArgusTest, ArgusTestRunComment, User, UserRoles


API_PREFIX = "/api/v1"
RUN_TYPE = "scylla-cluster-tests"


def _submit_run(api_client, fake_test: ArgusTest, *, run_id: str | None = None,
                build_number: int = 42) -> str:
    run_id = run_id or str(uuid4())
    payload = {
        "run_id": run_id,
        "job_name": fake_test.build_system_id,
        "job_url": f"http://ci.example.com/job/{build_number}",
        "started_by": "tr_user",
        "commit_id": "deadbeef",
        "origin_url": "http://example.com/repo.git",
        "branch_name": "main",
        "sct_config": {"cluster_backend": "aws"},
        "schema_version": "v8",
    }
    resp = api_client.post(
        f"{API_PREFIX}/client/testrun/{RUN_TYPE}/submit",
        json=payload,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    return run_id


@pytest.fixture
def submitted_run(api_client, fake_test):
    rid = _submit_run(api_client, fake_test)
    return rid, fake_test


# ---------------------------------------------------------------------------
# /run/<run_id>/type & /run/<run_type>/<run_id>
# ---------------------------------------------------------------------------

def test_get_type_for_run_returns_plugin_name(api_client, submitted_run):
    rid, _ = submitted_run
    resp = api_client.get(f"{API_PREFIX}/run/{rid}/type")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    assert resp.json()["response"]["run_type"] == RUN_TYPE


def test_get_testrun_returns_full_run_payload(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = api_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{rid}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    body = resp.json()["response"]
    assert str(body["id"]) == rid
    assert str(body["test_id"]) == str(fake_test.id)
    assert body["status"] == "created"


def test_get_testrun_unknown_id_returns_null(api_client):
    resp = api_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{uuid4()}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["response"] is None


# ---------------------------------------------------------------------------
# Status / investigation_status / assignee
# ---------------------------------------------------------------------------

def test_set_testrun_status_changes_status(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = api_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/status/set",
        json={"status": "running"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"

    follow = api_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{rid}")
    assert follow.json()["response"]["status"] == "running"


def test_set_testrun_status_missing_field_returns_error(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = api_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/status/set",
        json={},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_set_investigation_status_changes_value(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = api_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/investigation_status/set",
        json={"investigation_status": "in_progress"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    assert resp.json()["response"]["investigation_status"] == "in_progress"

    follow = api_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{rid}")
    assert follow.json()["response"]["investigation_status"] == "in_progress"


def test_set_investigation_status_missing_field_returns_error(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = api_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/investigation_status/set",
        json={},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_set_assignee_persists_user_id(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    assignee = User(id=uuid4(), username=f"assignee_{uuid4().hex[:8]}",
                    full_name="Assignee User", email="a@example.com",
                    password="x", roles=[UserRoles.User.value])
    assignee.save()

    with patch("argus.backend.service.notification_manager.NotificationManagerService.send_notification"):
        resp = api_client.post(
            f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/assignee/set",
            json={"assignee": str(assignee.id)},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    assert UUID(str(resp.json()["response"]["assignee"])) == assignee.id

    follow = api_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{rid}")
    assert UUID(str(follow.json()["response"]["assignee"])) == assignee.id


def test_set_assignee_placeholder_clears_assignee(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    assignee = User(id=uuid4(), username=f"assignee_{uuid4().hex[:8]}",
                    full_name="Assignee User 2", email="a2@example.com",
                    password="x", roles=[UserRoles.User.value])
    assignee.save()

    with patch("argus.backend.service.notification_manager.NotificationManagerService.send_notification"):
        # First assign so old_assignee resolves to a real user when we clear it.
        assigned = api_client.post(
            f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/assignee/set",
            json={"assignee": str(assignee.id)},
        )
        assert assigned.json()["status"] == "ok", assigned.text

        resp = api_client.post(
            f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/assignee/set",
            json={"assignee": "none-none-none"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    assert resp.json()["response"]["assignee"] is None

    follow = api_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{rid}")
    assert follow.json()["response"]["assignee"] is None


def test_set_assignee_missing_field_returns_error(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = api_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/assignee/set",
        json={},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def _post_comment(api_client, test_id, run_id, message="hello") -> dict:
    resp = api_client.post(
        f"{API_PREFIX}/test/{test_id}/run/{run_id}/comments/submit",
        json={"message": message, "reactions": {}, "mentions": []},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    return resp.json()["response"]


def test_post_run_comment_appears_in_listing(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    comments_after_post = _post_comment(api_client, fake_test.id, rid, "first comment")
    assert any(c["message"] == "first comment" for c in comments_after_post)

    listing = api_client.get(f"{API_PREFIX}/run/{rid}/comments")
    assert listing.status_code == 200
    assert listing.json()["status"] == "ok"
    messages = [c["message"] for c in listing.json()["response"]]
    assert "first comment" in messages


def test_get_single_comment_returns_correct_record(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    _post_comment(api_client, fake_test.id, rid, "lookup me")
    listing = api_client.get(f"{API_PREFIX}/run/{rid}/comments").json()["response"]
    [target] = [c for c in listing if c["message"] == "lookup me"]

    single = api_client.get(f"{API_PREFIX}/comment/{target['id']}/get")
    assert single.status_code == 200
    assert single.json()["status"] == "ok"
    assert single.json()["response"]["message"] == "lookup me"


def test_get_single_comment_unknown_returns_null(api_client):
    resp = api_client.get(f"{API_PREFIX}/comment/{uuid4()}/get")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["response"] is None


def test_update_run_comment_changes_message(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    _post_comment(api_client, fake_test.id, rid, "original")
    listing = api_client.get(f"{API_PREFIX}/run/{rid}/comments").json()["response"]
    [target] = [c for c in listing if c["message"] == "original"]

    resp = api_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/comment/{target['id']}/update",
        json={"message": "edited", "reactions": {}, "mentions": []},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    messages = [c["message"] for c in resp.json()["response"]]
    assert "edited" in messages
    assert "original" not in messages


def test_delete_run_comment_removes_record(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    _post_comment(api_client, fake_test.id, rid, "to be deleted")
    listing = api_client.get(f"{API_PREFIX}/run/{rid}/comments").json()["response"]
    [target] = [c for c in listing if c["message"] == "to be deleted"]

    resp = api_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/comment/{target['id']}/delete",
        json={},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    messages = [c["message"] for c in resp.json()["response"]]
    assert "to be deleted" not in messages
    with pytest.raises(DocumentNotFound):
        ArgusTestRunComment.get(id=UUID(target["id"]))


# ---------------------------------------------------------------------------
# Activity / fetch_results / get_runs_by_test_id_run_id / ignore_jobs
# ---------------------------------------------------------------------------

def test_test_run_activity_includes_status_change_event(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    # Trigger an event by changing the status.
    api_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/status/set",
        json={"status": "running"},
    )

    resp = api_client.get(f"{API_PREFIX}/run/{rid}/activity")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    body = resp.json()["response"]
    assert str(body["run_id"]) == rid
    assert len(body["raw_events"]) >= 1
    assert len(body["events"]) >= 1


def test_test_run_activity_empty_for_unknown_run(api_client):
    resp = api_client.get(f"{API_PREFIX}/run/{uuid4()}/activity")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["response"]["raw_events"] == []
    assert resp.json()["response"]["events"] == {}


def test_fetch_results_empty_for_run_without_results(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = api_client.get(f"{API_PREFIX}/run/{fake_test.id}/{rid}/fetch_results")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    assert resp.json()["tables"] == []


def test_get_runs_by_test_id_run_id_returns_build_metadata(api_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = api_client.post(
        f"{API_PREFIX}/get_runs_by_test_id_run_id",
        json=[[str(fake_test.id), rid]],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    runs = resp.json()["response"]["runs"]
    assert rid in runs
    assert runs[rid]["build_number"] == 42
    assert str(runs[rid]["test_id"]) == str(fake_test.id)


def test_ignore_jobs_marks_failed_runs_as_ignored(api_client, fake_test):
    # Create a finished/failed run so ignore_jobs has something to flip.
    rid = _submit_run(api_client, fake_test, build_number=99)
    api_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/status/set",
        json={"status": "failed"},
    )

    resp = api_client.post(
        f"{API_PREFIX}/ignore_jobs",
        json={"testId": str(fake_test.id), "reason": "flaky on purpose"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    assert resp.json()["response"]["affectedJobs"] >= 1

    follow = api_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{rid}")
    assert follow.json()["response"]["investigation_status"] == "ignored"


def test_ignore_jobs_empty_reason_returns_error(api_client, fake_test):
    resp = api_client.post(
        f"{API_PREFIX}/ignore_jobs",
        json={"testId": str(fake_test.id), "reason": ""},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


# ---------------------------------------------------------------------------
# Pytest endpoints
# ---------------------------------------------------------------------------

def _submit_pytest_result(api_client, name: str, *, status: str = "passed",
                          duration: float = 1.0, ts_offset: float = 0.0) -> None:
    ts = time.time() + ts_offset
    payload = {
        "name": name,
        "timestamp": ts,
        "session_timestamp": ts,
        "test_type": "dtest",
        "run_id": str(uuid4()),
        "status": status,
        "duration": duration,
        "markers": ["testrun_api"],
        "user_fields": {},
    }
    resp = api_client.post(
        f"{API_PREFIX}/client/testrun/pytest/result/submit",
        json=payload,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"


@pytest.fixture
def cleanup_pytest_rows():
    """Yield a list to which tests append pytest result names; rows are deleted on teardown."""
    names: list[str] = []
    yield names
    from argus.backend.models.pytest import PytestResultTable, PytestUserField
    for name in names:
        try:
            PytestResultTable.find(name=name).delete()
        except Exception:
            pass
        try:
            PytestUserField.find(name=name).delete()
        except Exception:
            pass


def test_get_pytest_test_results_returns_submitted_rows(api_client, cleanup_pytest_rows):
    test_name = f"tr_pytest::test_{uuid4().hex}"
    cleanup_pytest_rows.append(test_name)
    for i in range(2):
        _submit_pytest_result(api_client, test_name, ts_offset=i)

    resp = api_client.get(f"{API_PREFIX}/pytest/{test_name}/results")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    rows = resp.json()["response"]
    assert len(rows) == 2
    assert all(r["name"] == test_name for r in rows)


def test_get_pytest_test_field_stats_count(api_client, cleanup_pytest_rows):
    test_name = f"tr_pytest::test_count_{uuid4().hex}"
    cleanup_pytest_rows.append(test_name)
    for i in range(3):
        _submit_pytest_result(api_client, test_name, ts_offset=i)

    resp = api_client.get(f"{API_PREFIX}/pytest/{test_name}/stats/duration/count")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    body = resp.json()["response"]
    assert body[test_name]["duration"]["count"] == 3


# ---------------------------------------------------------------------------
# Issues endpoints (GitHub/Jira mocked at IssueService boundary)
# ---------------------------------------------------------------------------

def test_issues_submit_invokes_service(api_client, submitted_run, fake_test, mock_issue_service):
    rid, _ = submitted_run
    issue_url = "https://github.com/scylladb/scylladb/issues/4242"
    resp = api_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/issues/submit",
        json={"issue_url": issue_url},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    inst = mock_issue_service.return_value
    inst.submit.assert_called_once()
    kwargs = inst.submit.call_args.kwargs
    assert kwargs["issue_url"] == issue_url
    assert str(kwargs["test_id"]) == str(fake_test.id)
    assert str(kwargs["run_id"]) == rid


def test_issues_submit_for_event_invokes_service(api_client, submitted_run, fake_test, mock_issue_service):
    rid, _ = submitted_run
    event_id = str(uuid4())
    resp = api_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/issues/event/{event_id}/submit",
        json={"issue_url": "https://github.com/foo/bar/issues/1"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    inst = mock_issue_service.return_value
    inst.submit_for_sct_event.assert_called_once()
    assert str(inst.submit_for_sct_event.call_args.kwargs["event_id"]) == event_id


def test_issues_get_passes_query_args(api_client, fake_test, mock_issue_service):
    inst = mock_issue_service.return_value
    inst.get.return_value = [{"id": "abc", "title": "issue"}]
    resp = api_client.get(
        f"{API_PREFIX}/issues/get?filterKey=test&id={fake_test.id}&aggregateByIssue=1"
        "&productVersion=6.0&includeNoVersion=1"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    assert resp.json()["response"] == [{"id": "abc", "title": "issue"}]
    kwargs = inst.get.call_args.kwargs
    assert kwargs["filter_key"] == "test"
    assert str(kwargs["filter_id"]) == str(fake_test.id)
    assert kwargs["aggregate_by_issue"] is True
    assert kwargs["product_version"] == "6.0"
    assert kwargs["include_no_version"] is True


def test_issues_get_missing_filter_key_errors(api_client, mock_issue_service):
    resp = api_client.get(f"{API_PREFIX}/issues/get?id={uuid4()}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"


def test_issues_delete_invokes_service(api_client, mock_issue_service, logged_in_user):
    issue_id = str(uuid4())
    rid = str(uuid4())
    resp = api_client.post(
        f"{API_PREFIX}/issues/delete",
        json={"issue_id": issue_id, "run_id": rid},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    inst = mock_issue_service.return_value
    inst.delete.assert_called_once_with(issue_id=UUID(issue_id), run_id=UUID(rid), user=logged_in_user)


# ---------------------------------------------------------------------------
# Jenkins endpoints (JenkinsService mocked)
# ---------------------------------------------------------------------------

def test_jenkins_params_invokes_service(api_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.retrieve_job_parameters.return_value = [{"name": "BRANCH", "value": "main"}]
    resp = api_client.post(
        f"{API_PREFIX}/jenkins/params",
        json={"buildId": "job/foo", "buildNumber": 17},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    assert resp.json()["response"]["parameters"] == [{"name": "BRANCH", "value": "main"}]
    inst.retrieve_job_parameters.assert_called_once_with(build_id="job/foo", build_number=17, from_defaults=False)


def test_jenkins_build_returns_queue_item(api_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.build_job.return_value = 9999
    resp = api_client.post(
        f"{API_PREFIX}/jenkins/build",
        json={"buildId": "job/foo", "parameters": {"BRANCH": "main"}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["response"]["queueItem"] == 9999


def test_jenkins_queue_info_passes_int(api_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.get_queue_info.return_value = {"why": None, "url": "u"}
    resp = api_client.get(f"{API_PREFIX}/jenkins/queue_info?queueItem=42")
    assert resp.status_code == 200, resp.text
    assert resp.json()["response"]["queueItem"] == {"why": None, "url": "u"}
    inst.get_queue_info.assert_called_once_with(42)


def test_jenkins_queue_info_missing_param_errors(api_client, mock_jenkins_service):
    resp = api_client.get(f"{API_PREFIX}/jenkins/queue_info")
    assert resp.json()["status"] == "error"


def test_jenkins_clone_targets(api_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.get_releases_for_clone.return_value = [{"id": "r1", "name": "release-1"}]
    test_id = str(uuid4())
    resp = api_client.get(f"{API_PREFIX}/jenkins/clone/targets?testId={test_id}")
    assert resp.json()["response"]["targets"] == [{"id": "r1", "name": "release-1"}]


def test_jenkins_clone_groups(api_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.get_groups_for_release.return_value = [{"id": "g1", "name": "group-1"}]
    target_id = str(uuid4())
    resp = api_client.get(f"{API_PREFIX}/jenkins/clone/groups?targetId={target_id}")
    assert resp.json()["response"]["groups"] == [{"id": "g1", "name": "group-1"}]


def test_jenkins_clone_create(api_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.clone_job.return_value = "cloned/job/path"
    resp = api_client.post(
        f"{API_PREFIX}/jenkins/clone/create",
        json={
            "currentTestId": str(uuid4()),
            "newName": "clone-1",
            "target": "release-1",
            "group": "group-1",
            "advancedSettings": {},
        },
    )
    assert resp.json()["response"] == "cloned/job/path"


def test_jenkins_clone_build(api_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.clone_build_job.return_value = 5555
    resp = api_client.post(
        f"{API_PREFIX}/jenkins/clone/build",
        json={"buildId": "job/clone", "parameters": {}},
    )
    assert resp.json()["response"] == 5555


def test_jenkins_clone_settings_get(api_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.get_advanced_settings.return_value = {"timeout": 60}
    resp = api_client.get(f"{API_PREFIX}/jenkins/clone/settings?buildId=job/foo")
    assert resp.json()["response"] == {"timeout": 60}


def test_jenkins_clone_settings_validate(api_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.verify_job_settings.return_value = True
    resp = api_client.post(
        f"{API_PREFIX}/jenkins/clone/settings/validate",
        json={"buildId": "job/foo", "newSettings": {}},
    )
    assert resp.json()["response"] is True


# ---------------------------------------------------------------------------
# S3-backed routes (TestRunService methods mocked)
# ---------------------------------------------------------------------------

def test_download_log_redirects_to_s3_url(api_client, submitted_run, mock_s3):
    rid, _ = submitted_run
    resp = api_client.get(
        f"{API_PREFIX}/tests/{RUN_TYPE}/{rid}/log/example.log/download",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "test-bucket" in resp.headers["Location"]
    mock_s3.get_log.assert_called_once()
    kwargs = mock_s3.get_log.call_args.kwargs
    assert kwargs["plugin_name"] == RUN_TYPE
    assert str(kwargs["run_id"]) == rid
    assert kwargs["log_name"] == "example.log"


def test_proxy_screenshot_redirects(api_client, submitted_run, mock_s3):
    rid, _ = submitted_run
    resp = api_client.get(
        f"{API_PREFIX}/tests/{RUN_TYPE}/{rid}/screenshot/example.png",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "test-bucket" in resp.headers["Location"]
    mock_s3.proxy_stored_s3_image.assert_called_once()


# ---------------------------------------------------------------------------
# terminate_stuck_runs
# ---------------------------------------------------------------------------

def test_terminate_stuck_runs_returns_total(api_client):
    resp = api_client.post(f"{API_PREFIX}/terminate_stuck_runs")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ok"
    assert "total" in resp.json()["response"]
    assert isinstance(resp.json()["response"]["total"], int)
