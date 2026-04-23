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

from argus.backend.models.web import ArgusTest, ArgusTestRunComment, User, UserRoles


API_PREFIX = "/api/v1"
RUN_TYPE = "scylla-cluster-tests"


def _submit_run(flask_client, fake_test: ArgusTest, *, run_id: str | None = None,
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
    resp = flask_client.post(
        f"{API_PREFIX}/client/testrun/{RUN_TYPE}/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    return run_id


@pytest.fixture
def submitted_run(flask_client, fake_test):
    rid = _submit_run(flask_client, fake_test)
    return rid, fake_test


# ---------------------------------------------------------------------------
# /run/<run_id>/type & /run/<run_type>/<run_id>
# ---------------------------------------------------------------------------

def test_get_type_for_run_returns_plugin_name(flask_client, submitted_run):
    rid, _ = submitted_run
    resp = flask_client.get(f"{API_PREFIX}/run/{rid}/type")
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    assert resp.json["response"]["run_type"] == RUN_TYPE


def test_get_testrun_returns_full_run_payload(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = flask_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{rid}")
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    body = resp.json["response"]
    assert str(body["id"]) == rid
    assert str(body["test_id"]) == str(fake_test.id)
    assert body["status"] == "created"


def test_get_testrun_unknown_id_returns_null(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{uuid4()}")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert resp.json["response"] is None


# ---------------------------------------------------------------------------
# Status / investigation_status / assignee
# ---------------------------------------------------------------------------

def test_set_testrun_status_changes_status(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = flask_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/status/set",
        data=json.dumps({"status": "running"}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"

    follow = flask_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{rid}")
    assert follow.json["response"]["status"] == "running"


def test_set_testrun_status_missing_field_returns_error(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = flask_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/status/set",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_set_investigation_status_changes_value(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = flask_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/investigation_status/set",
        data=json.dumps({"investigation_status": "in_progress"}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    assert resp.json["response"]["investigation_status"] == "in_progress"

    follow = flask_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{rid}")
    assert follow.json["response"]["investigation_status"] == "in_progress"


def test_set_investigation_status_missing_field_returns_error(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = flask_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/investigation_status/set",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_set_assignee_persists_user_id(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    assignee = User(id=uuid4(), username=f"assignee_{uuid4().hex[:8]}",
                    full_name="Assignee User", email="a@example.com",
                    password="x", roles=[UserRoles.User.value])
    assignee.save()

    with patch("argus.backend.service.notification_manager.NotificationManagerService.send_notification"):
        resp = flask_client.post(
            f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/assignee/set",
            data=json.dumps({"assignee": str(assignee.id)}),
            content_type="application/json",
        )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    assert UUID(str(resp.json["response"]["assignee"])) == assignee.id

    follow = flask_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{rid}")
    assert UUID(str(follow.json["response"]["assignee"])) == assignee.id


def test_set_assignee_placeholder_clears_assignee(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    assignee = User(id=uuid4(), username=f"assignee_{uuid4().hex[:8]}",
                    full_name="Assignee User 2", email="a2@example.com",
                    password="x", roles=[UserRoles.User.value])
    assignee.save()

    with patch("argus.backend.service.notification_manager.NotificationManagerService.send_notification"):
        # First assign so old_assignee resolves to a real user when we clear it.
        assigned = flask_client.post(
            f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/assignee/set",
            data=json.dumps({"assignee": str(assignee.id)}),
            content_type="application/json",
        )
        assert assigned.json["status"] == "ok", assigned.text

        resp = flask_client.post(
            f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/assignee/set",
            data=json.dumps({"assignee": "none-none-none"}),
            content_type="application/json",
        )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    assert resp.json["response"]["assignee"] is None

    follow = flask_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{rid}")
    assert follow.json["response"]["assignee"] is None


def test_set_assignee_missing_field_returns_error(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = flask_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/assignee/set",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def _post_comment(flask_client, test_id, run_id, message="hello") -> dict:
    resp = flask_client.post(
        f"{API_PREFIX}/test/{test_id}/run/{run_id}/comments/submit",
        data=json.dumps({"message": message, "reactions": {}, "mentions": []}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    return resp.json["response"]


def test_post_run_comment_appears_in_listing(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    comments_after_post = _post_comment(flask_client, fake_test.id, rid, "first comment")
    assert any(c["message"] == "first comment" for c in comments_after_post)

    listing = flask_client.get(f"{API_PREFIX}/run/{rid}/comments")
    assert listing.status_code == 200
    assert listing.json["status"] == "ok"
    messages = [c["message"] for c in listing.json["response"]]
    assert "first comment" in messages


def test_get_single_comment_returns_correct_record(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    _post_comment(flask_client, fake_test.id, rid, "lookup me")
    listing = flask_client.get(f"{API_PREFIX}/run/{rid}/comments").json["response"]
    [target] = [c for c in listing if c["message"] == "lookup me"]

    single = flask_client.get(f"{API_PREFIX}/comment/{target['id']}/get")
    assert single.status_code == 200
    assert single.json["status"] == "ok"
    assert single.json["response"]["message"] == "lookup me"


def test_get_single_comment_unknown_returns_null(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/comment/{uuid4()}/get")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert resp.json["response"] is None


def test_update_run_comment_changes_message(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    _post_comment(flask_client, fake_test.id, rid, "original")
    listing = flask_client.get(f"{API_PREFIX}/run/{rid}/comments").json["response"]
    [target] = [c for c in listing if c["message"] == "original"]

    resp = flask_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/comment/{target['id']}/update",
        data=json.dumps({"message": "edited", "reactions": {}, "mentions": []}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    messages = [c["message"] for c in resp.json["response"]]
    assert "edited" in messages
    assert "original" not in messages


def test_delete_run_comment_removes_record(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    _post_comment(flask_client, fake_test.id, rid, "to be deleted")
    listing = flask_client.get(f"{API_PREFIX}/run/{rid}/comments").json["response"]
    [target] = [c for c in listing if c["message"] == "to be deleted"]

    resp = flask_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/comment/{target['id']}/delete",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    messages = [c["message"] for c in resp.json["response"]]
    assert "to be deleted" not in messages
    with pytest.raises(ArgusTestRunComment.DoesNotExist):
        ArgusTestRunComment.get(id=UUID(target["id"]))


# ---------------------------------------------------------------------------
# Activity / fetch_results / get_runs_by_test_id_run_id / ignore_jobs
# ---------------------------------------------------------------------------

def test_test_run_activity_includes_status_change_event(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    # Trigger an event by changing the status.
    flask_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/status/set",
        data=json.dumps({"status": "running"}),
        content_type="application/json",
    )

    resp = flask_client.get(f"{API_PREFIX}/run/{rid}/activity")
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    body = resp.json["response"]
    assert str(body["run_id"]) == rid
    assert len(body["raw_events"]) >= 1
    assert len(body["events"]) >= 1


def test_test_run_activity_empty_for_unknown_run(flask_client):
    resp = flask_client.get(f"{API_PREFIX}/run/{uuid4()}/activity")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    assert resp.json["response"]["raw_events"] == []
    assert resp.json["response"]["events"] == {}


def test_fetch_results_empty_for_run_without_results(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = flask_client.get(f"{API_PREFIX}/run/{fake_test.id}/{rid}/fetch_results")
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    assert resp.json["tables"] == []


def test_get_runs_by_test_id_run_id_returns_build_metadata(flask_client, submitted_run, fake_test):
    rid, _ = submitted_run
    resp = flask_client.post(
        f"{API_PREFIX}/get_runs_by_test_id_run_id",
        data=json.dumps([[str(fake_test.id), rid]]),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    runs = resp.json["response"]["runs"]
    assert rid in runs
    assert runs[rid]["build_number"] == 42
    assert str(runs[rid]["test_id"]) == str(fake_test.id)


def test_ignore_jobs_marks_failed_runs_as_ignored(flask_client, fake_test):
    # Create a finished/failed run so ignore_jobs has something to flip.
    rid = _submit_run(flask_client, fake_test, build_number=99)
    flask_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/status/set",
        data=json.dumps({"status": "failed"}),
        content_type="application/json",
    )

    resp = flask_client.post(
        f"{API_PREFIX}/ignore_jobs",
        data=json.dumps({"testId": str(fake_test.id), "reason": "flaky on purpose"}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    assert resp.json["response"]["affectedJobs"] >= 1

    follow = flask_client.get(f"{API_PREFIX}/run/{RUN_TYPE}/{rid}")
    assert follow.json["response"]["investigation_status"] == "ignored"


def test_ignore_jobs_empty_reason_returns_error(flask_client, fake_test):
    resp = flask_client.post(
        f"{API_PREFIX}/ignore_jobs",
        data=json.dumps({"testId": str(fake_test.id), "reason": ""}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


# ---------------------------------------------------------------------------
# Pytest endpoints
# ---------------------------------------------------------------------------

def _submit_pytest_result(flask_client, name: str, *, status: str = "passed",
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
    resp = flask_client.post(
        f"{API_PREFIX}/client/testrun/pytest/result/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"


def test_get_pytest_test_results_returns_submitted_rows(flask_client):
    test_name = f"tr_pytest::test_{uuid4().hex}"
    for i in range(2):
        _submit_pytest_result(flask_client, test_name, ts_offset=i)

    resp = flask_client.get(f"{API_PREFIX}/pytest/{test_name}/results")
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    rows = resp.json["response"]
    assert len(rows) == 2
    assert all(r["name"] == test_name for r in rows)


def test_get_pytest_test_field_stats_count(flask_client):
    test_name = f"tr_pytest::test_count_{uuid4().hex}"
    for i in range(3):
        _submit_pytest_result(flask_client, test_name, ts_offset=i)

    resp = flask_client.get(f"{API_PREFIX}/pytest/{test_name}/stats/duration/count")
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    body = resp.json["response"]
    assert body[test_name]["duration"]["count"] == 3


# ---------------------------------------------------------------------------
# Issues endpoints (GitHub/Jira mocked at IssueService boundary)
# ---------------------------------------------------------------------------

def test_issues_submit_invokes_service(flask_client, submitted_run, fake_test, mock_issue_service):
    rid, _ = submitted_run
    issue_url = "https://github.com/scylladb/scylladb/issues/4242"
    resp = flask_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/issues/submit",
        data=json.dumps({"issue_url": issue_url}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    inst = mock_issue_service.return_value
    inst.submit.assert_called_once()
    kwargs = inst.submit.call_args.kwargs
    assert kwargs["issue_url"] == issue_url
    assert str(kwargs["test_id"]) == str(fake_test.id)
    assert str(kwargs["run_id"]) == rid


def test_issues_submit_for_event_invokes_service(flask_client, submitted_run, fake_test, mock_issue_service):
    rid, _ = submitted_run
    event_id = str(uuid4())
    resp = flask_client.post(
        f"{API_PREFIX}/test/{fake_test.id}/run/{rid}/issues/event/{event_id}/submit",
        data=json.dumps({"issue_url": "https://github.com/foo/bar/issues/1"}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    inst = mock_issue_service.return_value
    inst.submit_for_sct_event.assert_called_once()
    assert str(inst.submit_for_sct_event.call_args.kwargs["event_id"]) == event_id


def test_issues_get_passes_query_args(flask_client, fake_test, mock_issue_service):
    inst = mock_issue_service.return_value
    inst.get.return_value = [{"id": "abc", "title": "issue"}]
    resp = flask_client.get(
        f"{API_PREFIX}/issues/get?filterKey=test&id={fake_test.id}&aggregateByIssue=1"
        "&productVersion=6.0&includeNoVersion=1"
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    assert resp.json["response"] == [{"id": "abc", "title": "issue"}]
    kwargs = inst.get.call_args.kwargs
    assert kwargs["filter_key"] == "test"
    assert str(kwargs["filter_id"]) == str(fake_test.id)
    assert kwargs["aggregate_by_issue"] is True
    assert kwargs["product_version"] == "6.0"
    assert kwargs["include_no_version"] is True


def test_issues_get_missing_filter_key_errors(flask_client, mock_issue_service):
    resp = flask_client.get(f"{API_PREFIX}/issues/get?id={uuid4()}")
    assert resp.status_code == 200
    assert resp.json["status"] == "error"


def test_issues_delete_invokes_service(flask_client, mock_issue_service):
    issue_id = str(uuid4())
    rid = str(uuid4())
    resp = flask_client.post(
        f"{API_PREFIX}/issues/delete",
        data=json.dumps({"issue_id": issue_id, "run_id": rid}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    inst = mock_issue_service.return_value
    inst.delete.assert_called_once_with(issue_id=issue_id, run_id=rid)


# ---------------------------------------------------------------------------
# Jenkins endpoints (JenkinsService mocked)
# ---------------------------------------------------------------------------

def test_jenkins_params_invokes_service(flask_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.retrieve_job_parameters.return_value = [{"name": "BRANCH", "value": "main"}]
    resp = flask_client.post(
        f"{API_PREFIX}/jenkins/params",
        data=json.dumps({"buildId": "job/foo", "buildNumber": 17}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    assert resp.json["response"]["parameters"] == [{"name": "BRANCH", "value": "main"}]
    inst.retrieve_job_parameters.assert_called_once_with(build_id="job/foo", build_number=17)


def test_jenkins_build_returns_queue_item(flask_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.build_job.return_value = 9999
    resp = flask_client.post(
        f"{API_PREFIX}/jenkins/build",
        data=json.dumps({"buildId": "job/foo", "parameters": {"BRANCH": "main"}}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json["response"]["queueItem"] == 9999


def test_jenkins_queue_info_passes_int(flask_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.get_queue_info.return_value = {"why": None, "url": "u"}
    resp = flask_client.get(f"{API_PREFIX}/jenkins/queue_info?queueItem=42")
    assert resp.status_code == 200, resp.text
    assert resp.json["response"]["queueItem"] == {"why": None, "url": "u"}
    inst.get_queue_info.assert_called_once_with(42)


def test_jenkins_queue_info_missing_param_errors(flask_client, mock_jenkins_service):
    resp = flask_client.get(f"{API_PREFIX}/jenkins/queue_info")
    assert resp.json["status"] == "error"


def test_jenkins_clone_targets(flask_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.get_releases_for_clone.return_value = [{"id": "r1", "name": "release-1"}]
    test_id = str(uuid4())
    resp = flask_client.get(f"{API_PREFIX}/jenkins/clone/targets?testId={test_id}")
    assert resp.json["response"]["targets"] == [{"id": "r1", "name": "release-1"}]


def test_jenkins_clone_groups(flask_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.get_groups_for_release.return_value = [{"id": "g1", "name": "group-1"}]
    target_id = str(uuid4())
    resp = flask_client.get(f"{API_PREFIX}/jenkins/clone/groups?targetId={target_id}")
    assert resp.json["response"]["groups"] == [{"id": "g1", "name": "group-1"}]


def test_jenkins_clone_create(flask_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.clone_job.return_value = "cloned/job/path"
    resp = flask_client.post(
        f"{API_PREFIX}/jenkins/clone/create",
        data=json.dumps({
            "currentTestId": str(uuid4()),
            "newName": "clone-1",
            "target": "release-1",
            "group": "group-1",
            "advancedSettings": {},
        }),
        content_type="application/json",
    )
    assert resp.json["response"] == "cloned/job/path"


def test_jenkins_clone_build(flask_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.clone_build_job.return_value = 5555
    resp = flask_client.post(
        f"{API_PREFIX}/jenkins/clone/build",
        data=json.dumps({"buildId": "job/clone", "parameters": {}}),
        content_type="application/json",
    )
    assert resp.json["response"] == 5555


def test_jenkins_clone_settings_get(flask_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.get_advanced_settings.return_value = {"timeout": 60}
    resp = flask_client.get(f"{API_PREFIX}/jenkins/clone/settings?buildId=job/foo")
    assert resp.json["response"] == {"timeout": 60}


def test_jenkins_clone_settings_validate(flask_client, mock_jenkins_service):
    inst = mock_jenkins_service.return_value
    inst.verify_job_settings.return_value = True
    resp = flask_client.post(
        f"{API_PREFIX}/jenkins/clone/settings/validate",
        data=json.dumps({"buildId": "job/foo", "newSettings": {}}),
        content_type="application/json",
    )
    assert resp.json["response"] is True


# ---------------------------------------------------------------------------
# S3-backed routes (TestRunService methods mocked)
# ---------------------------------------------------------------------------

def test_download_log_redirects_to_s3_url(flask_client, submitted_run, mock_s3):
    rid, _ = submitted_run
    resp = flask_client.get(
        f"{API_PREFIX}/tests/{RUN_TYPE}/{rid}/log/example.log/download"
    )
    assert resp.status_code == 302
    assert "test-bucket" in resp.headers["Location"]
    mock_s3.get_log.assert_called_once()
    kwargs = mock_s3.get_log.call_args.kwargs
    assert kwargs["plugin_name"] == RUN_TYPE
    assert str(kwargs["run_id"]) == rid
    assert kwargs["log_name"] == "example.log"


def test_proxy_screenshot_redirects(flask_client, submitted_run, mock_s3):
    rid, _ = submitted_run
    resp = flask_client.get(
        f"{API_PREFIX}/tests/{RUN_TYPE}/{rid}/screenshot/example.png"
    )
    assert resp.status_code == 302
    assert "test-bucket" in resp.headers["Location"]
    mock_s3.proxy_stored_s3_image.assert_called_once()


# ---------------------------------------------------------------------------
# terminate_stuck_runs
# ---------------------------------------------------------------------------

def test_terminate_stuck_runs_returns_total(flask_client):
    resp = flask_client.post(f"{API_PREFIX}/terminate_stuck_runs")
    assert resp.status_code == 200, resp.text
    assert resp.json["status"] == "ok"
    assert "total" in resp.json["response"]
    assert isinstance(resp.json["response"]["total"], int)
