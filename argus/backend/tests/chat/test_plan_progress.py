import json
from unittest.mock import MagicMock, patch
from uuid import uuid1

import pytest

from argus.backend.service.chat.entity import resolve_entity
from argus.backend.service.chat.llm import ToolCall
from argus.backend.service.chat.tools import ToolContext, run_tool
from argus.backend.service.jenkins_service import JenkinsService
from argus.backend.service.planner_service import CreatePlanPayload, PlanningService
from argus.backend.tests.release_summary.helpers import seed_release, submit_run, unique

pytestmark = pytest.mark.docker_required

VERSION = "2036.1.0~rc2"


async def call(ctx: ToolContext, name: str, **arguments):
    outcome = await run_tool(ctx, ToolCall("c1", name, json.dumps(arguments)))
    return outcome, (json.loads(outcome.content) if not outcome.error else outcome.content)


@pytest.fixture
async def seeded(release_manager_service, client_service):
    seeded = await seed_release(release_manager_service, test_count=3)
    await submit_run(client_service, seeded.tests[0], VERSION, "failed")
    await submit_run(client_service, seeded.tests[1], VERSION, "passed")
    return seeded


@pytest.fixture
async def ctx(seeded, logged_in_user):
    return ToolContext(entity=await resolve_entity("release", seeded.release.id), user=logged_in_user, node=uuid1())


async def new_plan(seeded, user, target_version: str = VERSION):
    first, second, third = seeded.tests
    payload = CreatePlanPayload(
        name=unique("plan"), description="", owner=user.id, participants=[], target_version=target_version,
        release_id=seeded.release.id, tests=[test.id for test in seeded.tests], groups=[], assignments={},
        options={str(first.id): {"labels": ["week1"]}, str(second.id): {"labels": ["sanity"]},
                 str(third.id): {"labels": ["Week1"]}})
    return await PlanningService().create_plan(payload, user)


@pytest.fixture
async def plan(seeded, logged_in_user):
    return await new_plan(seeded, logged_in_user)


@pytest.fixture
def jenkins():
    instance = MagicMock(spec=JenkinsService, name="JenkinsService")
    instance.retrieve_job_parameters.side_effect = lambda build_id, build_number, **_: [
        {"name": "backend", "value": "aws", "choices": ["aws", "gce"]}]
    with patch("argus.backend.service.chat.actions.JenkinsService", return_value=instance):
        yield instance


def started(outcome) -> set[str]:
    return {test["test_id"] for test in outcome.action["proposal"]["tests"]}


async def test_progress_counts_each_state_of_the_plan(ctx, plan, seeded):
    _, progress = await call(ctx, "get_plan_progress", plan=plan.name, version=VERSION)

    assert progress["version"] == VERSION
    assert progress["counts"] == {"passed": 1, "failed": 1, "aborted": 0, "in_progress": 0, "not_run": 1}
    states = {entry["test"].split("/")[-1]: entry["state"] for entry in progress["tests"]}
    assert states == {seeded.tests[0].name: "failed", seeded.tests[1].name: "passed",
                      seeded.tests[2].name: "not_run"}


async def test_progress_of_a_label_takes_the_target_version(ctx, plan):
    _, progress = await call(ctx, "get_plan_progress", plan=plan.name, labels=["week1"])

    assert progress["version"] == VERSION
    assert progress["counts"]["failed"] == 1 and progress["counts"]["not_run"] == 1
    assert progress["counts"]["passed"] == 0


async def test_progress_without_any_version_asks_for_one(ctx, seeded, logged_in_user):
    plan = await new_plan(seeded, logged_in_user, target_version="")

    outcome, message = await call(ctx, "get_plan_progress", plan=plan.name)

    assert outcome.error and "Name a version" in message


async def test_a_plan_start_takes_only_the_tests_in_the_states(ctx, plan, seeded, jenkins):
    outcome, _ = await call(ctx, "execute_plan_tests", plan=plan.name, only=["not_run"])

    assert started(outcome) == {str(seeded.tests[2].id)}


async def test_a_plan_start_without_labels_takes_the_whole_plan(ctx, plan, seeded, jenkins):
    outcome, _ = await call(ctx, "execute_plan_tests", plan=plan.name)

    assert started(outcome) == {str(test.id) for test in seeded.tests}


async def test_a_plan_start_that_leaves_nothing_names_the_counts(ctx, plan, jenkins):
    outcome, message = await call(ctx, "execute_plan_tests", plan=plan.name, labels=["week1"], only=["passed"])

    assert outcome.error and "failed 1" in message and "not_run 1" in message
    jenkins.retrieve_job_parameters.assert_not_called()


async def test_a_dry_run_lists_the_states(ctx, plan, seeded):
    _, listed = await call(ctx, "execute_plan_tests", plan=plan.name, labels=["week1"], only=["failed"],
                           dry_run=True)

    assert [(entry["test"].split("/")[-1], entry["state"]) for entry in listed["tests"]] == [
        (seeded.tests[0].name, "failed")]


async def test_read_release_narrows_to_a_plan_label(ctx, plan, seeded):
    _, release = await call(ctx, "read_release", plan=plan.name, labels=["sanity"])

    assert [test["name"] for test in release["tests"]] == [seeded.tests[1].name]


async def test_get_summary_narrows_to_a_plan_label(ctx, plan, seeded):
    _, summary = await call(ctx, "get_summary", version=VERSION, plan=plan.name, labels=["week1"])

    [version] = summary["releases"][0]["families"][0]["versions"]
    assert {test["test"] for test in version["tests"]} == {seeded.tests[0].name, seeded.tests[2].name}
    assert version["counts"]["failed"] == 1 and version["counts"]["passed"] == 0


async def test_get_assignees_lists_the_plan_tests(ctx, plan, seeded):
    _, assignees = await call(ctx, "get_assignees", plan=plan.name)

    assert len(assignees["tests"]) == 3


async def test_a_plan_start_leaves_out_the_tests_of_a_disabled_group(ctx, plan, seeded, jenkins,
                                                                     release_manager_service):
    disabled = await release_manager_service.create_group(unique("group"), "disabled", build_system_id=unique("g"),
                                                         release_id=seeded.release.id)
    await release_manager_service.batch_move_tests(disabled.id, [seeded.tests[2].id])
    await release_manager_service.toggle_group_enabled(disabled.id, False)

    outcome, _ = await call(ctx, "execute_plan_tests", plan=plan.name)

    assert started(outcome) == {str(seeded.tests[0].id), str(seeded.tests[1].id)}


async def test_labels_without_a_plan_ask_for_the_plan(ctx):
    outcome, message = await call(ctx, "read_release", labels=["week1"])

    assert outcome.error and "Name the plan" in message
