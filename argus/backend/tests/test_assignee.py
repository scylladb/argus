from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from argus.backend.tests.conftest import g

from argus.backend.models.plan import ArgusReleasePlan
from argus.backend.models.web import ArgusTest, User, UserRoles
from argus.backend.plugins.core import JENKINS_LOOKUP_TIMEOUT_SECONDS
from argus.backend.plugins.generic.model import GenericRun
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.backend.service.testrun import TestRunService

SUBMIT_ENDPOINT = "/api/v1/client/testrun/scylla-cluster-tests/submit"
NOTIFICATION_TARGET = "argus.backend.service.notification_manager.NotificationManagerService.send_notification"
JENKINS_TARGET = "argus.backend.plugins.core.JenkinsService"


@contextmanager
def jenkins_returns(requested_by_user: str | None):
    """Patch the whole JenkinsService class, because its constructor needs app config the tests do not set"""
    with patch(JENKINS_TARGET) as service_class:
        service_class.return_value.get_requested_by_user = AsyncMock(return_value=requested_by_user)
        yield service_class.return_value.get_requested_by_user


@pytest.fixture(autouse=True)
def jenkins_service():
    with patch(JENKINS_TARGET) as service_class:
        service_class.return_value.get_requested_by_user = AsyncMock(return_value=None)
        yield service_class


@pytest.fixture
async def fake_test(release_manager_service) -> ArgusTest:
    name = f"assignee_{time.time_ns()}"
    release = await release_manager_service.create_release(name, name, False)
    group = await release_manager_service.create_group(name, name, build_system_id=name, release_id=str(release.id))
    return await release_manager_service.create_test(name, name, name, name, group_id=str(group.id),
                                               release_id=str(release.id), plugin_name="scylla-cluster-tests")


@pytest.fixture
def make_user():
    """Return a factory that creates and saves an Argus user with a unique username and email"""
    async def _make_user(prefix: str = "user") -> User:
        suffix = uuid.uuid4().hex[:8]
        user = User(
            id=uuid.uuid4(),
            username=f"{prefix}_{suffix}",
            full_name=f"{prefix} test user",
            email=f"{prefix}_{suffix}@scylladb.com",
            password="test_password",
            roles=[UserRoles.User.value], registration_date=datetime.now(UTC),
        )
        await user.save()
        return user
    return _make_user


@pytest.fixture
async def test_user(make_user):
    """Create and save a test user for assignee tests"""
    return await make_user("assignee_user")


@pytest.fixture
async def saved_g_user():
    """Save the g.user to the database for assignee tests"""
    g.user.password = "test_password"
    g.user.roles = [role.value if hasattr(role, 'value') else role for role in g.user.roles]
    await g.user.save()
    return g.user


@pytest.fixture
def submit_sct_run(api_client, fake_test):
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
        resp = api_client.post(SUBMIT_ENDPOINT, json=payload)
        assert resp.status_code == 200, resp.json()
        assert resp.json()["status"] == "ok"
        return run_id
    return _submit


@pytest.fixture
def sct_run_for_assignee(submit_sct_run, fake_test):
    """Create an SCT run that can be used for assignee tests"""
    return submit_sct_run(), fake_test.id


@pytest.fixture
async def make_plan(fake_test):
    plans: list[ArgusReleasePlan] = []

    async def _make_plan(owner: User, assignee_id: uuid.UUID | None = None, **plan_fields) -> ArgusReleasePlan:
        plan = ArgusReleasePlan(
            name=f"assignee_plan_{uuid.uuid4().hex[:8]}",
            description="assignee test plan",
            owner=owner.id,
            target_version=f"1.0.0-{uuid.uuid4().hex[:8]}",
            release_id=fake_test.release_id,
            tests=[fake_test.id],
            assignee_mapping={fake_test.id: assignee_id or owner.id},
            **plan_fields,
        )
        await plan.save()
        plans.append(plan)
        return plan

    yield _make_plan

    for plan in plans:
        await plan.delete()


@pytest.fixture
async def planned_investigator(make_user, make_plan):
    investigator = await make_user("investigator")
    await make_plan(owner=investigator)
    return investigator


async def test_unassign_testrun(api_client, sct_run_for_assignee, test_user):
    """Test that unassigning a testrun works without error"""
    run_id, test_id = sct_run_for_assignee

    with patch(NOTIFICATION_TARGET):
        assign_payload = {"assignee": str(test_user.id)}
        resp = api_client.post(
            f"/api/v1/test/{test_id}/run/{run_id}/assignee/set",
            json=assign_payload,
        )
        assert resp.status_code == 200, f"Assign failed: {resp.json()}"
        assert resp.json()["status"] == "ok"
        assert resp.json()["response"]["assignee"] == str(test_user.id)

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee == test_user.id

    with patch(NOTIFICATION_TARGET) as mock_notify:
        unassign_payload = {"assignee": TestRunService.ASSIGNEE_PLACEHOLDER}
        resp = api_client.post(
            f"/api/v1/test/{test_id}/run/{run_id}/assignee/set",
            json=unassign_payload,
        )
        assert resp.status_code == 200, f"Unassign failed: {resp.json()}"
        assert resp.json()["status"] == "ok"
        assert resp.json()["response"]["assignee"] is None

        mock_notify.assert_not_called()

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee is None


def test_assign_testrun_to_self(api_client, sct_run_for_assignee, saved_g_user):
    """Test that assigning a testrun to yourself doesn't send notification"""
    run_id, test_id = sct_run_for_assignee

    with patch(NOTIFICATION_TARGET) as mock_notify:
        assign_payload = {"assignee": str(g.user.id)}
        resp = api_client.post(
            f"/api/v1/test/{test_id}/run/{run_id}/assignee/set",
            json=assign_payload,
        )
        assert resp.status_code == 200, f"Assign to self failed: {resp.json()}"
        assert resp.json()["status"] == "ok"

        mock_notify.assert_not_called()


def test_assign_testrun_to_other(api_client, sct_run_for_assignee, test_user, saved_g_user):
    """Test that assigning a testrun to someone else sends notification"""
    run_id, test_id = sct_run_for_assignee

    with patch(NOTIFICATION_TARGET) as mock_notify:
        assign_payload = {"assignee": str(test_user.id)}
        resp = api_client.post(
            f"/api/v1/test/{test_id}/run/{run_id}/assignee/set",
            json=assign_payload,
        )
        assert resp.status_code == 200, f"Assign to other failed: {resp.json()}"
        assert resp.json()["status"] == "ok"
        assert resp.json()["response"]["assignee"] == str(test_user.id)

        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs["receiver"] == test_user.id


async def test_run_auto_assigned_to_triggerer(submit_sct_run, make_user):
    """A submitted run is assigned to the started_by user when that user exists in Argus."""
    triggerer = await make_user("triggerer")

    run_id = submit_sct_run(started_by=triggerer.username, job_url="http://example.com/job/auto")

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee == triggerer.id, "run should be assigned to the person who triggered it"


async def test_run_unassigned_when_triggerer_unknown(submit_sct_run, fake_test):
    """A run stays unassigned when started_by matches no Argus user and Jenkins returns nothing."""
    with jenkins_returns(None) as mock_jenkins:
        run_id = submit_sct_run(started_by="ghost_user_that_does_not_exist",
                                job_url=f"http://example.com/job/{fake_test.build_system_id}/98/")

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee is None, "run should remain unassigned when started_by user does not exist"
    mock_jenkins.assert_called_once_with(build_id=fake_test.build_system_id, build_number=98)


async def test_investigation_assignee_takes_priority_over_triggerer(submit_sct_run, make_user, planned_investigator):
    """The investigation duty person wins over the started_by user."""
    triggerer = await make_user("just_triggerer")

    run_id = submit_sct_run(started_by=triggerer.username, job_url="http://example.com/job/investigation")

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee == planned_investigator.id, \
        "run should be assigned to the investigation duty person, not the triggerer"


async def test_run_assigned_via_jenkins_fallback_when_started_by_unknown(submit_sct_run, make_user, fake_test):
    """When started_by doesn't match any Argus user, fall back to REQUESTED_BY_USER from Jenkins."""
    jenkins_user = await make_user("jenkins_user")
    requested_by_user = jenkins_user.email.split("@")[0]

    with jenkins_returns(requested_by_user):
        run_id = submit_sct_run(
            started_by="ghost_user_not_in_argus",
            job_url=f"http://example.com/job/{fake_test.build_system_id}/99/",
        )

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee == jenkins_user.id, "run should be assigned to the user returned by Jenkins REQUESTED_BY_USER"


async def test_run_unassigned_when_jenkins_fallback_returns_unknown_user(submit_sct_run, fake_test):
    """When REQUESTED_BY_USER from Jenkins doesn't match any Argus user either, leave the run unassigned."""
    with jenkins_returns("also_unknown_jenkins_user"):
        run_id = submit_sct_run(
            started_by="ghost_user_not_in_argus",
            job_url=f"http://example.com/job/{fake_test.build_system_id}/100/",
        )

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee is None, "run should remain unassigned when Jenkins user is also not in Argus"


async def test_run_unassigned_when_jenkins_fallback_fails(submit_sct_run, fake_test):
    """When Jenkins is unreachable, silently fall through and leave the run unassigned."""
    with patch(JENKINS_TARGET, side_effect=Exception("Jenkins unreachable")):
        run_id = submit_sct_run(
            started_by="ghost_user_not_in_argus",
            job_url=f"http://example.com/job/{fake_test.build_system_id}/101/",
        )

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee is None, "run should remain unassigned when Jenkins fallback raises"


async def test_started_by_takes_priority_over_jenkins_fallback(submit_sct_run, make_user, fake_test):
    """started_by should be used when it resolves to a known user; Jenkins is not queried."""
    triggerer = await make_user("real_triggerer")

    with jenkins_returns("should_not_be_used") as mock_jenkins:
        run_id = submit_sct_run(
            started_by=triggerer.username,
            job_url=f"http://example.com/job/{fake_test.build_system_id}/102/",
        )

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee == triggerer.id, "run should be assigned to the started_by user"
    mock_jenkins.assert_not_called()


@pytest.mark.parametrize("plan_fields", [
    pytest.param({"completed": True}, id="completed"),
    pytest.param({"ends_at": datetime.now(UTC) - timedelta(days=1)}, id="expired"),
])
async def test_inactive_plan_does_not_take_priority_over_triggerer(submit_sct_run, make_user, make_plan, plan_fields):
    await make_plan(owner=await make_user("former_investigator"), **plan_fields)
    triggerer = await make_user("triggerer_after_plan")

    run_id = submit_sct_run(started_by=triggerer.username, job_url="http://example.com/job/inactive-plan")

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee == triggerer.id, "an inactive plan should not take the run from the triggerer"


async def test_plan_with_future_end_still_takes_priority(submit_sct_run, make_user, make_plan):
    investigator = await make_user("future_investigator")
    await make_plan(owner=investigator, ends_at=datetime.now(UTC) + timedelta(days=1))
    triggerer = await make_user("triggerer_future_plan")

    run_id = submit_sct_run(started_by=triggerer.username, job_url="http://example.com/job/future-plan")

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee == investigator.id, "an active plan should keep priority over the triggerer"


async def test_plan_assignee_missing_from_argus_falls_back_to_triggerer(submit_sct_run, make_user, make_plan):
    await make_plan(owner=await make_user("plan_owner"), assignee_id=uuid.uuid4())
    triggerer = await make_user("triggerer_stale_plan")

    run_id = submit_sct_run(started_by=triggerer.username, job_url="http://example.com/job/stale-plan")

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee == triggerer.id, "a missing plan assignee should fall back to the triggerer"


async def test_jenkins_fallback_skips_ambiguous_local_part(submit_sct_run, make_user, fake_test):
    first = await make_user("same_local")
    local_part = first.email.split("@")[0]
    second = await make_user("other_domain")
    second.email = f"{local_part}@partner.example.com"
    await second.save()

    with jenkins_returns(local_part):
        run_id = submit_sct_run(
            started_by="ghost_user_not_in_argus",
            job_url=f"http://example.com/job/{fake_test.build_system_id}/103/",
        )

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee is None, "an ambiguous REQUESTED_BY_USER should leave the run unassigned"


async def test_jenkins_fallback_matches_email_outside_scylladb_domain(submit_sct_run, make_user, fake_test):
    partner = await make_user("partner_user")
    partner.email = f"{partner.username}@partner.example.com"
    await partner.save()

    with jenkins_returns(partner.username):
        run_id = submit_sct_run(
            started_by="ghost_user_not_in_argus",
            job_url=f"http://example.com/job/{fake_test.build_system_id}/104/",
        )

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee == partner.id, "the Jenkins fallback should match a unique local part on any domain"


def test_jenkins_lookup_uses_short_timeout(submit_sct_run, fake_test, jenkins_service):
    submit_sct_run(started_by="ghost_user_not_in_argus",
                   job_url=f"http://example.com/job/{fake_test.build_system_id}/105/")

    jenkins_service.assert_called_once_with(timeout=JENKINS_LOOKUP_TIMEOUT_SECONDS)


async def test_assignee_lookup_failure_leaves_run_unassigned(submit_sct_run):
    with patch.object(User, "exists_by_name", side_effect=RuntimeError("read timeout")):
        run_id = submit_sct_run(started_by="anyone", job_url="http://example.com/job/lookup-failure")

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee is None, "an assignee lookup failure should not fail the submission"


async def test_plan_lookup_failure_falls_back_to_triggerer(submit_sct_run, make_user):
    triggerer = await make_user("triggerer_plan_failure")

    with patch.object(SCTTestRun, "get_assignment", side_effect=RuntimeError("read timeout")):
        run_id = submit_sct_run(started_by=triggerer.username, job_url="http://example.com/job/plan-failure")

    run = await SCTTestRun.get(id=uuid.UUID(run_id))
    assert run.assignee == triggerer.id, "a plan lookup failure should fall back to the triggerer"


@pytest.mark.parametrize("build_number", [None, -1, 0])
async def test_jenkins_not_queried_without_build_number(jenkins_service, build_number):
    run = SCTTestRun.model_construct(
        id=uuid.uuid4(),
        build_id=f"sct_{uuid.uuid4().hex[:8]}",
        build_job_url="",
        build_number=build_number,
    )

    assert await run.get_assignee("ghost_user_not_in_argus") is None
    jenkins_service.assert_not_called()


async def test_non_jenkins_plugin_does_not_query_jenkins(make_user, jenkins_service):
    run = GenericRun.model_construct(
        id=uuid.uuid4(),
        build_id=f"generic_{uuid.uuid4().hex[:8]}",
        build_job_url="http://example.com/job/generic/7/",
        build_number=7,
    )

    assert await run.get_assignee("ghost_user_not_in_argus") is None
    jenkins_service.assert_not_called()
