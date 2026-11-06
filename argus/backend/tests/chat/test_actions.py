import asyncio
import json
from unittest.mock import MagicMock, patch
from uuid import uuid1

import pytest

from argus.backend.service.chat import tasks as chat_tasks
from argus.backend.service.chat.actions import ChatActionError, execute
from argus.backend.service.chat.entity import resolve_entity
from argus.backend.service.chat.history import ChatHistoryError, ChatHistoryService
from argus.backend.service.chat.hub import ChatHub
from argus.backend.service.chat.llm import ToolCall
from argus.backend.service.chat.service import ChatService
from argus.backend.service.chat.tools import ToolContext, run_tool
from argus.backend.service.issue_service import IssueService
from argus.backend.service.jenkins_service import JenkinsService
from argus.backend.service.planner_service import CreatePlanPayload, PlanningService
from argus.backend.tests.chat.helpers import seed_entity_release, seed_view, text_turn, tool_turn
from argus.backend.tests.release_summary.helpers import submit_run, unique

pytestmark = pytest.mark.docker_required

JOBS = {
    # build_system_id suffix -> job parameters of the last build
    0: [{"name": "backend", "value": "aws", "choices": ["aws", "gce"]},
        {"name": "scylla_version", "value": "2025.1.0"},
        {"name": "region", "value": "us-east-1"}],
    1: [{"name": "backend", "value": "aws", "choices": ["aws", "azure"]},
        {"name": "scylla_version", "value": "2025.1.0"}],
}


@pytest.fixture
def jenkins(seeded):
    by_job = {test.build_system_id: JOBS[index] for index, test in enumerate(seeded.tests)}
    instance = MagicMock(spec=JenkinsService, name="JenkinsService")
    instance.retrieve_job_parameters.side_effect = lambda build_id, build_number, **_: [
        dict(param) for param in by_job[build_id]]
    instance.build_job.return_value = 777
    instance.next_build_number.return_value = 42
    with patch("argus.backend.service.chat.actions.JenkinsService", return_value=instance):
        yield instance


@pytest.fixture
def issues():
    instance = MagicMock(spec=IssueService, name="IssueService")
    instance.submit.return_value = {"id": "11111111-1111-1111-1111-111111111111", "key": "SCYLLA-9"}
    instance.get.return_value = [{"id": "22222222-2222-2222-2222-222222222222", "key": "SCYLLA-5",
                                  "url": "https://jira.test/browse/SCYLLA-5", "title": "crash"}]
    instance.delete.return_value = {"deleted": "22222222-2222-2222-2222-222222222222"}
    with patch("argus.backend.service.chat.actions.IssueService", return_value=instance):
        yield instance


@pytest.fixture
async def seeded(release_manager_service, client_service):
    seeded = await seed_entity_release(release_manager_service)
    seeded.run = await submit_run(client_service, seeded.tests[0], "2037.1.0~rc1", "failed")
    return seeded


@pytest.fixture
async def ctx(seeded, logged_in_user):
    return ToolContext(entity=await resolve_entity("release", seeded.release.id), user=logged_in_user, node=uuid1())


async def call(ctx, name: str, **arguments):
    return await run_tool(ctx, ToolCall("c1", name, json.dumps(arguments)))


async def test_a_start_is_checked_against_each_jobs_choices(ctx, seeded, jenkins):
    outcome = await call(ctx, "execute_tests", tests=[seeded.tests[0].name, seeded.tests[1].name],
                         params={"backend": "gce"})

    action = outcome.action
    assert action["kind"] == "execute_tests"
    [proposed] = action["proposal"]["tests"]
    assert proposed["build_system_id"] == seeded.tests[0].build_system_id
    assert proposed["params"] == {"backend": "gce", "scylla_version": "2025.1.0", "region": "us-east-1"}
    assert proposed["overrides"] == {"backend": "gce"}
    [rejected] = action["rejected"]
    assert rejected["test"] == f"{seeded.group.name}/{seeded.tests[1].name}"
    assert "gce" in rejected["reason"] and "aws, azure" in rejected["reason"]
    assert "confirm" in outcome.content.lower()
    jenkins.build_job.assert_not_called()


async def test_an_unknown_parameter_rejects_the_test(ctx, seeded, jenkins):
    outcome = await call(ctx, "execute_tests", tests=[seeded.tests[1].name], params={"region": "eu-west-1"})

    assert outcome.action is None
    assert outcome.error and "region" in outcome.content


async def test_a_second_version_source_is_rejected(ctx, seeded, jenkins):
    outcome = await call(ctx, "execute_tests", tests=[seeded.tests[0].name], params={"scylla_repo": "x"})

    assert outcome.error and "scylla_repo" in outcome.content


async def test_a_view_cannot_start_a_test_outside_it(seeded, jenkins, logged_in_user):
    view = await seed_view(logged_in_user, [seeded.tests[1]])
    ctx = ToolContext(entity=await resolve_entity("view", view.id), user=logged_in_user, node=uuid1())

    outcome = await call(ctx, "execute_tests", tests=[seeded.tests[0].name])

    assert outcome.error and "scope" in outcome.content
    jenkins.retrieve_job_parameters.assert_not_called()


async def test_plan_labels_select_tests_and_groups(ctx, seeded, jenkins, logged_in_user, release_manager_service):
    other_group = await release_manager_service.create_group(unique("group"), "other", build_system_id=unique("g"),
                                                            release_id=seeded.release.id)
    payload = CreatePlanPayload(
        name=unique("plan"), description="", owner=logged_in_user.id, participants=[], target_version="2037.1",
        release_id=seeded.release.id, tests=[seeded.tests[0].id], groups=[seeded.group.id, other_group.id],
        assignments={}, options={str(seeded.tests[0].id): {"labels": ["week1"]},
                                 str(seeded.group.id): {"labels": ["Week1", "sanity"]},
                                 str(other_group.id): {"labels": ["perf"]}})
    plan = await PlanningService().create_plan(payload, logged_in_user)

    union = await call(ctx, "execute_plan_tests", plan=plan.name, labels=["week1"])
    both = await call(ctx, "execute_plan_tests", plan=str(plan.id), labels=["week1", "sanity"], match_all=True)
    nothing = await call(ctx, "execute_plan_tests", plan=plan.name, labels=["nightly"])

    assert {test["test_id"] for test in union.action["proposal"]["tests"]} == {
        str(seeded.tests[0].id), str(seeded.tests[1].id)}
    assert len(both.action["proposal"]["tests"]) == 2
    assert nothing.error and "perf" in nothing.content and "sanity" in nothing.content


async def test_link_and_unlink_are_proposed(ctx, seeded, issues):
    linked = await call(ctx, "link_issue", run=str(seeded.run), url="https://jira.test/browse/SCYLLA-9")
    unlinked = await call(ctx, "unlink_issue", run=str(seeded.run), issue="SCYLLA-5")

    assert linked.action["kind"] == "link_issue"
    assert linked.action["proposal"]["issue_url"] == "https://jira.test/browse/SCYLLA-9"
    assert unlinked.action["proposal"]["issue_id"] == "22222222-2222-2222-2222-222222222222"
    issues.submit.assert_not_called()
    issues.delete.assert_not_called()


async def card_from_chat(seeded, chat_model, logged_in_user, call_name: str, arguments: dict):
    entity = await resolve_entity("release", seeded.release.id)
    service = ChatService(ChatHub())
    chat_model.turns = [tool_turn((call_name, arguments)), text_turn("Confirm the card")]
    await service.send(entity, "do it", logged_in_user)
    await chat_tasks.drain()
    _, nodes = await ChatHistoryService(entity).read()
    return entity, service, next(node for node in nodes if node.role == "action")


async def test_confirming_starts_each_job_once_as_the_confirming_user(seeded, jenkins, chat_model, logged_in_user):
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user, "execute_tests",
                                                 {"tests": [seeded.tests[0].name], "params": {"backend": "gce"}})

    running = await service.confirm(entity, card.node, logged_in_user)
    with pytest.raises(ChatActionError):
        await service.confirm(entity, card.node, logged_in_user)
    await chat_tasks.drain()

    _, nodes = await ChatHistoryService(entity).read()
    done = next(node for node in nodes if node.node == card.node)
    action = json.loads(done.action)
    assert running["action"]["state"] == "running"
    assert done.action_state == "done"
    assert action["confirmed_by"] == str(logged_in_user.id)
    assert action["results"] == [{"build_system_id": seeded.tests[0].build_system_id,
                                  "test": f"{seeded.group.name}/{seeded.tests[0].name}", "queue_item": 777,
                                  "build_number": 42, "error": None}]
    jenkins.build_job.assert_called_once()
    kwargs = jenkins.build_job.call_args.kwargs
    assert kwargs["params"]["backend"] == "gce" and kwargs["requested_by"] == logged_in_user
    with pytest.raises(ChatActionError):
        await service.dismiss(entity, card.node, logged_in_user)


async def test_a_jenkins_failure_is_recorded_per_test(seeded, jenkins, chat_model, logged_in_user):
    jenkins.build_job.side_effect = RuntimeError("Jenkins is down")
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user, "execute_tests",
                                                 {"tests": [seeded.tests[0].name]})

    await service.confirm(entity, card.node, logged_in_user)
    await chat_tasks.drain()

    _, nodes = await ChatHistoryService(entity).read()
    action = json.loads(next(node for node in nodes if node.node == card.node).action)
    assert "Jenkins is down" in action["results"][0]["error"]


async def test_a_dismissed_card_cannot_be_confirmed(seeded, jenkins, chat_model, logged_in_user):
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user, "execute_tests",
                                                 {"tests": [seeded.tests[0].name]})

    dismissed = await service.dismiss(entity, card.node, logged_in_user)
    with pytest.raises(ChatActionError):
        await service.confirm(entity, card.node, logged_in_user)

    assert dismissed["action"]["state"] == "dismissed"
    jenkins.build_job.assert_not_called()


async def test_a_confirmed_link_submits_the_issue(seeded, issues, chat_model, logged_in_user):
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user, "link_issue",
                                                 {"run": str(seeded.run),
                                                  "url": "https://jira.test/browse/SCYLLA-9"})

    await service.confirm(entity, card.node, logged_in_user)
    await chat_tasks.drain()

    issues.submit.assert_called_once_with(issue_url="https://jira.test/browse/SCYLLA-9",
                                          test_id=seeded.tests[0].id, run_id=seeded.run, user=logged_in_user)
    _, nodes = await ChatHistoryService(entity).read()
    assert next(node for node in nodes if node.node == card.node).action_state == "done"


async def test_a_card_under_an_undone_question_cannot_be_confirmed(seeded, jenkins, chat_model, logged_in_user):
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user, "execute_tests",
                                                 {"tests": [seeded.tests[0].name]})

    await service.undo(entity)
    with pytest.raises(ChatActionError, match="undone"):
        await service.confirm(entity, card.node, logged_in_user)
    jenkins.build_job.assert_not_called()


async def test_a_shutdown_while_a_card_runs_closes_the_card(seeded, jenkins, chat_model, logged_in_user):
    started = asyncio.Event()

    async def hang(**_):
        started.set()
        await asyncio.Event().wait()

    jenkins.build_job.side_effect = hang
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user, "execute_tests",
                                                 {"tests": [seeded.tests[0].name]})

    await service.confirm(entity, card.node, logged_in_user)
    await started.wait()
    await chat_tasks.shutdown()

    _, nodes = await ChatHistoryService(entity).read()
    closed = next(node for node in nodes if node.node == card.node)
    assert closed.action_state == "done"
    assert "server stopped" in json.loads(closed.action)["results"][0]["error"]


async def test_a_card_confirmed_later_acts_only_within_the_chat_now(seeded, jenkins, issues, chat_model,
                                                                    logged_in_user):
    entity, _, start = await card_from_chat(seeded, chat_model, logged_in_user, "execute_tests",
                                            {"tests": [seeded.tests[0].name]})
    await card_from_chat(seeded, chat_model, logged_in_user, "link_issue",
                         {"run": str(seeded.run), "url": "https://jira.test/browse/SCYLLA-9"})
    _, nodes = await ChatHistoryService(entity).read()
    link = next(node for node in nodes if node.role == "action" and json.loads(node.action)["kind"] == "link_issue")
    view = await resolve_entity("view", (await seed_view(logged_in_user, [seeded.tests[1]])).id)

    started = await execute(view, start, json.loads(start.action), logged_in_user)
    linked = await execute(view, link, json.loads(link.action), logged_in_user)

    assert "no longer in this chat's scope" in started["results"][0]["error"]
    assert "outside" in linked["results"][0]["error"]
    jenkins.build_job.assert_not_called()
    issues.submit.assert_not_called()


async def test_a_start_whose_job_changed_since_the_card_is_not_started(seeded, jenkins, chat_model, logged_in_user):
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user, "execute_tests",
                                                 {"tests": [seeded.tests[0].name], "params": {"backend": "gce"}})
    jenkins.retrieve_job_parameters.side_effect = lambda build_id, build_number, **_: [
        {"name": "backend", "value": "aws", "choices": ["aws"]}, {"name": "scylla_version", "value": "2025.1.0"},
        {"name": "region", "value": "us-east-1"}]

    await service.confirm(entity, card.node, logged_in_user)
    await chat_tasks.drain()

    _, nodes = await ChatHistoryService(entity).read()
    action = json.loads(next(node for node in nodes if node.node == card.node).action)
    assert action["results"][0]["error"].startswith("Not started: gce is not a choice of backend")
    jenkins.build_job.assert_not_called()


async def test_undo_waits_for_a_running_card(seeded, jenkins, chat_model, logged_in_user):
    release = asyncio.Event()

    async def held(**_):
        await release.wait()
        return 777

    jenkins.build_job.side_effect = held
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user, "execute_tests",
                                                 {"tests": [seeded.tests[0].name]})
    await service.confirm(entity, card.node, logged_in_user)

    with pytest.raises(ChatHistoryError, match="still running"):
        await service.undo(entity)
    release.set()
    await chat_tasks.drain()
    await service.undo(entity)
