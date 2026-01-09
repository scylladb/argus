import json
import uuid
from unittest.mock import patch

import pytest
from flask import g

from argus.backend.models.web import User, UserRoles
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
