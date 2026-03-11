import json
import uuid
from datetime import datetime, timedelta, UTC
from unittest.mock import patch

import pytest
from flask import g

from argus.backend.models.web import ArgusSchedule, ArgusScheduleAssignee, ArgusScheduleTest, User, UserRoles
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.testrun import TestRunService


@pytest.fixture
def test_user():
    """Create and save a test user for assignee tests"""
    user = User(
        id=uuid.uuid4(),
        username=f"assignee_user_{uuid.uuid4().hex[:8]}",
        full_name="Assignee Test User",
        email=f"assignee_{uuid.uuid4().hex[:8]}@scylladb.com",
        password="test_password",
        roles=[UserRoles.User.value],
    )
    user.save()
    return user


@pytest.fixture
def saved_g_user():
    """Save the g.user to the database for assignee tests"""
    g.user.password = "test_password"
    # Convert roles to string values for saving
    g.user.roles = [role.value if hasattr(role, 'value') else role for role in g.user.roles]
    g.user.save()
    return g.user


@pytest.fixture
def sct_run_for_assignee(flask_client, fake_test):
    """Create an SCT run that can be used for assignee tests"""
    run_id = str(uuid.uuid4())
    payload = {
        "run_id": run_id,
        "job_name": fake_test.build_system_id,
        "job_url": "http://example.com/job/1",
        "started_by": "test_user",
        "commit_id": "deadbeef",
        "origin_url": "http://example.com/repo.git",
        "branch_name": "main",
        "sct_config": {"cluster_backend": "aws"},
        "schema_version": "v8",
    }
    resp = flask_client.post(
        "/api/v1/client/testrun/scylla-cluster-tests/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"
    return run_id, fake_test.id


def test_unassign_testrun(flask_client, sct_run_for_assignee, test_user):
    """Test that unassigning a testrun works without error"""
    run_id, test_id = sct_run_for_assignee

    # First, assign to a user
    with patch('argus.backend.service.notification_manager.NotificationManagerService.send_notification'):
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
    with patch('argus.backend.service.notification_manager.NotificationManagerService.send_notification') as mock_notify:
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

    # Assign to self (g.user from conftest)
    with patch('argus.backend.service.notification_manager.NotificationManagerService.send_notification') as mock_notify:
        assign_payload = {"assignee": str(g.user.id)}
        resp = flask_client.post(
            f"/api/v1/test/{test_id}/run/{run_id}/assignee/set",
            data=json.dumps(assign_payload),
            content_type="application/json",
        )
        assert resp.status_code == 200, f"Assign to self failed: {resp.json}"
        assert resp.json["status"] == "ok"

        # Verify no notification was sent when assigning to self
        mock_notify.assert_not_called()


def test_assign_testrun_to_other(flask_client, sct_run_for_assignee, test_user, saved_g_user):
    """Test that assigning a testrun to someone else sends notification"""
    run_id, test_id = sct_run_for_assignee

    # Assign to another user
    with patch('argus.backend.service.notification_manager.NotificationManagerService.send_notification') as mock_notify:
        assign_payload = {"assignee": str(test_user.id)}
        resp = flask_client.post(
            f"/api/v1/test/{test_id}/run/{run_id}/assignee/set",
            data=json.dumps(assign_payload),
            content_type="application/json",
        )
        assert resp.status_code == 200, f"Assign to other failed: {resp.json}"
        assert resp.json["status"] == "ok"
        assert resp.json["response"]["assignee"] == str(test_user.id)

        # Verify notification was sent when assigning to someone else
        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs["receiver"] == test_user.id


def test_run_auto_assigned_to_triggerer(flask_client, fake_test):
    triggerer = User(
        id=uuid.uuid4(),
        username=f"triggerer_{uuid.uuid4().hex[:8]}",
        full_name="Triggerer User",
        email=f"trigger_{uuid.uuid4().hex[:8]}@scylladb.com",
        password="test_password",
        roles=[UserRoles.User.value],
    )
    triggerer.save()

    run_id = str(uuid.uuid4())
    payload = {
        "run_id": run_id,
        "job_name": fake_test.build_system_id,
        "job_url": "http://example.com/job/auto",
        "started_by": triggerer.username,
        "commit_id": "cafebabe",
        "origin_url": "http://example.com/repo.git",
        "branch_name": "main",
        "sct_config": {"cluster_backend": "aws"},
        "schema_version": "v8",
    }
    resp = flask_client.post(
        "/api/v1/client/testrun/scylla-cluster-tests/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.json
    assert resp.json["status"] == "ok"

    run = SCTTestRun.get(id=run_id)
    assert run.assignee == triggerer.id, "run should be assigned to the person who triggered it"


def test_run_unassigned_when_triggerer_unknown(flask_client, fake_test):
    run_id = str(uuid.uuid4())
    payload = {
        "run_id": run_id,
        "job_name": fake_test.build_system_id,
        "job_url": "http://example.com/job/unknown",
        "started_by": "ghost_user_that_does_not_exist",
        "commit_id": "00000000",
        "origin_url": "http://example.com/repo.git",
        "branch_name": "main",
        "sct_config": {"cluster_backend": "aws"},
        "schema_version": "v8",
    }
    resp = flask_client.post(
        "/api/v1/client/testrun/scylla-cluster-tests/submit",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.json
    assert resp.json["status"] == "ok"

    run = SCTTestRun.get(id=run_id)
    assert run.assignee is None, "run should remain unassigned when started_by user does not exist"


def test_investigation_assignee_takes_priority_over_triggerer(flask_client, fake_test):
    investigator = User(
        id=uuid.uuid4(),
        username=f"investigator_{uuid.uuid4().hex[:8]}",
        full_name="Investigator User",
        email=f"inv_{uuid.uuid4().hex[:8]}@scylladb.com",
        password="test_password",
        roles=[UserRoles.User.value],
    )
    investigator.save()

    triggerer = User(
        id=uuid.uuid4(),
        username=f"just_triggerer_{uuid.uuid4().hex[:8]}",
        full_name="Just Triggerer",
        email=f"justtrigger_{uuid.uuid4().hex[:8]}@scylladb.com",
        password="test_password",
        roles=[UserRoles.User.value],
    )
    triggerer.save()

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

    try:
        run_id = str(uuid.uuid4())
        payload = {
            "run_id": run_id,
            "job_name": fake_test.build_system_id,
            "job_url": "http://example.com/job/investigation",
            "started_by": triggerer.username,
            "commit_id": "deadc0de",
            "origin_url": "http://example.com/repo.git",
            "branch_name": "main",
            "sct_config": {"cluster_backend": "aws"},
            "schema_version": "v8",
        }
        resp = flask_client.post(
            "/api/v1/client/testrun/scylla-cluster-tests/submit",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.json
        assert resp.json["status"] == "ok"

        run = SCTTestRun.get(id=run_id)
        assert run.assignee == investigator.id, "run should be assigned to the investigation duty person, not the triggerer"
        assert run.assignee != triggerer.id
    finally:
        schedule_assignee.delete()
        schedule_test.delete()
        schedule.delete()
