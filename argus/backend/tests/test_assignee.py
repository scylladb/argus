import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, UTC
from unittest.mock import patch

import pytest
from flask import g

from argus.backend.models.web import ArgusSchedule, ArgusScheduleAssignee, ArgusScheduleTest, User, UserRoles
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.testrun import TestRunService

SUBMIT_ENDPOINT = "/api/v1/client/testrun/scylla-cluster-tests/submit"
NOTIFICATION_TARGET = "argus.backend.service.notification_manager.NotificationManagerService.send_notification"
JENKINS_TARGET = "argus.backend.plugins.core.JenkinsService"


@contextmanager
def jenkins_returns(requested_by_user: str | None):
    """Patch the whole JenkinsService class, because its constructor needs app config the tests do not set"""
    with patch(JENKINS_TARGET) as service_class:
        service_class.return_value.get_requested_by_user.return_value = requested_by_user
        yield service_class.return_value.get_requested_by_user


@pytest.fixture
def make_user():
    """Return a factory that creates and saves an Argus user with a unique username and email"""
    def _make_user(prefix: str = "user") -> User:
        suffix = uuid.uuid4().hex[:8]
        user = User(
            id=uuid.uuid4(),
            username=f"{prefix}_{suffix}",
            full_name=f"{prefix} test user",
            email=f"{prefix}_{suffix}@scylladb.com",
            password="test_password",
            roles=[UserRoles.User.value],
        )
        user.save()
        return user
    return _make_user


@pytest.fixture
def test_user(make_user):
    """Create and save a test user for assignee tests"""
    return make_user("assignee_user")


@pytest.fixture
def saved_g_user():
    """Save the g.user to the database for assignee tests"""
    g.user.password = "test_password"
    # Convert roles to string values for saving
    g.user.roles = [role.value if hasattr(role, 'value') else role for role in g.user.roles]
    g.user.save()
    return g.user


@pytest.fixture
def submit_sct_run(flask_client, fake_test):
    """Return a factory that submits an SCT run for the fake test and returns its run id"""
    def _submit(started_by: str = "test_user", job_url: str = "http://example.com/job/1") -> str:
        run_id = str(uuid.uuid4())
        payload = {
            "run_id": run_id,
            "job_name": fake_test.build_system_id,
            "job_url": job_url,
            "started_by": started_by,
            "commit_id": "deadbeef",
            "origin_url": "http://example.com/repo.git",
            "branch_name": "main",
            "sct_config": {"cluster_backend": "aws"},
            "schema_version": "v8",
        }
        resp = flask_client.post(SUBMIT_ENDPOINT, data=json.dumps(payload), content_type="application/json")
        assert resp.status_code == 200, resp.json
        assert resp.json["status"] == "ok"
        return run_id
    return _submit


@pytest.fixture
def sct_run_for_assignee(submit_sct_run, fake_test):
    """Create an SCT run that can be used for assignee tests"""
    return submit_sct_run(), fake_test.id


@pytest.fixture
def scheduled_investigator(make_user, fake_test):
    """Put a user on investigation duty for the fake test and remove the schedule afterwards"""
    investigator = make_user("investigator")
    now = datetime.now(UTC)

    schedule = ArgusSchedule(
        release_id=fake_test.release_id,
        period_start=now - timedelta(days=1),
        period_end=now + timedelta(days=1),
    )
    schedule.save()

    schedule_test = ArgusScheduleTest(
        release_id=fake_test.release_id,
        test_id=fake_test.id,
        schedule_id=schedule.id,
    )
    schedule_test.save()

    schedule_assignee = ArgusScheduleAssignee(
        assignee=investigator.id,
        release_id=fake_test.release_id,
        schedule_id=schedule.id,
    )
    schedule_assignee.save()

    yield investigator

    schedule_assignee.delete()
    schedule_test.delete()
    schedule.delete()


def test_unassign_testrun(flask_client, sct_run_for_assignee, test_user):
    """Test that unassigning a testrun works without error"""
    run_id, test_id = sct_run_for_assignee

    # First, assign to a user
    with patch(NOTIFICATION_TARGET):
        assign_payload = {"assignee": str(test_user.id)}
        resp = flask_client.post(
            f"/api/v1/test/{test_id}/run/{run_id}/assignee/set",
            data=json.dumps(assign_payload),
            content_type="application/json",
        )
        assert resp.status_code == 200, f"Assign failed: {resp.json}"
        assert resp.json["status"] == "ok"
        assert resp.json["response"]["assignee"] == str(test_user.id)

    # Verify assignment persisted
    run = SCTTestRun.get(id=run_id)
    assert run.assignee == test_user.id

    # Now unassign (this is what was causing the error)
    with patch(NOTIFICATION_TARGET) as mock_notify:
        unassign_payload = {"assignee": TestRunService.ASSIGNEE_PLACEHOLDER}
        resp = flask_client.post(
            f"/api/v1/test/{test_id}/run/{run_id}/assignee/set",
            data=json.dumps(unassign_payload),
            content_type="application/json",
        )
        assert resp.status_code == 200, f"Unassign failed: {resp.json}"
        assert resp.json["status"] == "ok"
        assert resp.json["response"]["assignee"] is None

        # Verify no notification was sent when unassigning
        mock_notify.assert_not_called()

    # Verify unassignment persisted
    run = SCTTestRun.get(id=run_id)
    assert run.assignee is None


def test_assign_testrun_to_self(flask_client, sct_run_for_assignee, saved_g_user):
    """Test that assigning a testrun to yourself doesn't send notification"""
    run_id, test_id = sct_run_for_assignee

    with patch(NOTIFICATION_TARGET) as mock_notify:
        assign_payload = {"assignee": str(g.user.id)}
        resp = flask_client.post(
            f"/api/v1/test/{test_id}/run/{run_id}/assignee/set",
            data=json.dumps(assign_payload),
            content_type="application/json",
        )
        assert resp.status_code == 200, f"Assign to self failed: {resp.json}"
        assert resp.json["status"] == "ok"

        mock_notify.assert_not_called()


def test_assign_testrun_to_other(flask_client, sct_run_for_assignee, test_user, saved_g_user):
    """Test that assigning a testrun to someone else sends notification"""
    run_id, test_id = sct_run_for_assignee

    with patch(NOTIFICATION_TARGET) as mock_notify:
        assign_payload = {"assignee": str(test_user.id)}
        resp = flask_client.post(
            f"/api/v1/test/{test_id}/run/{run_id}/assignee/set",
            data=json.dumps(assign_payload),
            content_type="application/json",
        )
        assert resp.status_code == 200, f"Assign to other failed: {resp.json}"
        assert resp.json["status"] == "ok"
        assert resp.json["response"]["assignee"] == str(test_user.id)

        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs["receiver"] == test_user.id


def test_run_auto_assigned_to_triggerer(submit_sct_run, make_user):
    """A submitted run is assigned to the started_by user when that user exists in Argus."""
    triggerer = make_user("triggerer")

    run_id = submit_sct_run(started_by=triggerer.username, job_url="http://example.com/job/auto")

    run = SCTTestRun.get(id=run_id)
    assert run.assignee == triggerer.id, "run should be assigned to the person who triggered it"


def test_run_unassigned_when_triggerer_unknown(submit_sct_run):
    """A run stays unassigned when started_by matches no Argus user and Jenkins returns nothing."""
    with jenkins_returns(None):
        run_id = submit_sct_run(started_by="ghost_user_that_does_not_exist",
                                job_url="http://example.com/job/unknown")

    run = SCTTestRun.get(id=run_id)
    assert run.assignee is None, "run should remain unassigned when started_by user does not exist"


def test_investigation_assignee_takes_priority_over_triggerer(submit_sct_run, make_user, scheduled_investigator):
    """The investigation duty person wins over the started_by user."""
    triggerer = make_user("just_triggerer")

    run_id = submit_sct_run(started_by=triggerer.username, job_url="http://example.com/job/investigation")

    run = SCTTestRun.get(id=run_id)
    assert run.assignee == scheduled_investigator.id, \
        "run should be assigned to the investigation duty person, not the triggerer"
    assert run.assignee != triggerer.id


def test_run_assigned_via_jenkins_fallback_when_started_by_unknown(submit_sct_run, make_user, fake_test):
    """When started_by doesn't match any Argus user, fall back to REQUESTED_BY_USER from Jenkins."""
    jenkins_user = make_user("jenkins_user")
    # Jenkins holds the email local part only, so the lookup appends the scylladb.com domain
    requested_by_user = jenkins_user.email.split("@")[0]

    with jenkins_returns(requested_by_user):
        run_id = submit_sct_run(
            started_by="ghost_user_not_in_argus",
            job_url=f"http://example.com/job/{fake_test.build_system_id}/99/",
        )

    run = SCTTestRun.get(id=run_id)
    assert run.assignee == jenkins_user.id, "run should be assigned to the user returned by Jenkins REQUESTED_BY_USER"


def test_run_unassigned_when_jenkins_fallback_returns_unknown_user(submit_sct_run, fake_test):
    """When REQUESTED_BY_USER from Jenkins doesn't match any Argus user either, leave the run unassigned."""
    with jenkins_returns("also_unknown_jenkins_user"):
        run_id = submit_sct_run(
            started_by="ghost_user_not_in_argus",
            job_url=f"http://example.com/job/{fake_test.build_system_id}/100/",
        )

    run = SCTTestRun.get(id=run_id)
    assert run.assignee is None, "run should remain unassigned when Jenkins user is also not in Argus"


def test_run_unassigned_when_jenkins_fallback_fails(submit_sct_run, fake_test):
    """When Jenkins is unreachable, silently fall through and leave the run unassigned."""
    with patch(JENKINS_TARGET, side_effect=Exception("Jenkins unreachable")):
        run_id = submit_sct_run(
            started_by="ghost_user_not_in_argus",
            job_url=f"http://example.com/job/{fake_test.build_system_id}/101/",
        )

    run = SCTTestRun.get(id=run_id)
    assert run.assignee is None, "run should remain unassigned when Jenkins fallback raises"


def test_started_by_takes_priority_over_jenkins_fallback(submit_sct_run, make_user, fake_test):
    """started_by should be used when it resolves to a known user; Jenkins is not queried."""
    triggerer = make_user("real_triggerer")

    with jenkins_returns("should_not_be_used") as mock_jenkins:
        run_id = submit_sct_run(
            started_by=triggerer.username,
            job_url=f"http://example.com/job/{fake_test.build_system_id}/102/",
        )

    run = SCTTestRun.get(id=run_id)
    assert run.assignee == triggerer.id, "run should be assigned to the started_by user"
    mock_jenkins.assert_not_called()
