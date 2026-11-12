import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid1

import pytest

from argus.backend.service.chat import tasks as chat_tasks
from argus.backend.service.chat.actions import ChatActionError
from argus.backend.service.chat.entity import resolve_entity
from argus.backend.service.chat.history import ChatHistoryService
from argus.backend.service.chat.hub import ChatHub
from argus.backend.service.chat.llm import ToolCall
from argus.backend.service.chat.service import ChatService
from argus.backend.service.chat.tools import ToolContext, run_tool
from argus.backend.service.jenkins_service import JenkinsService
from argus.backend.service.planner_service import CreatePlanPayload, PlanningService
from argus.backend.tests.chat.helpers import seed_entity_release, text_turn, tool_turn
from argus.backend.tests.release_summary.helpers import unique

pytestmark = pytest.mark.docker_required

LAST_BUILD = [
    {"name": "backend", "value": "aws"},
    {"name": "region", "value": "eu-west-1"},
    {"name": "gce_datacenter", "value": ""},
    {"name": "scylla_version", "value": ""},
    {"name": "scylla_repo", "value": "https://downloads.scylladb.com/rpm/scylla.repo"},
    {"name": "scylla_ami_id", "value": ""},
    {"name": "azure_image_db", "value": ""},
    {"name": "oci_image_db", "value": ""},
    {"name": "byo_scylla_repo", "value": ""},
    {"name": "byo_scylla_branch", "value": ""},
    {"name": "provision_type", "value": "spot",
     "description": "How the instances are <span class=\"fw-bold\">provisioned</span>"},
    {"name": "email_recipients", "value": ""},
    {"name": "post_behavior_db_nodes", "value": "destroy", "choices": ["destroy", "keep", "keep-on-failure"]},
]


def job(build_number: int | None, from_defaults: bool) -> list[dict]:
    params = [dict(param) for param in LAST_BUILD]
    by_name = {param["name"]: param for param in params}
    if from_defaults:
        by_name["scylla_version"]["value"] = "master:latest"
        by_name["scylla_repo"]["value"] = ""
    if build_number == 7:
        by_name["region"]["value"] = "us-east-1"
    return params


@pytest.fixture
def jenkins():
    instance = MagicMock(spec=JenkinsService, name="JenkinsService")
    instance.retrieve_job_parameters.side_effect = lambda build_id, build_number, from_defaults=False: job(
        build_number, from_defaults)
    instance.build_job.return_value = 777
    instance.next_build_number.return_value = 42
    with patch("argus.backend.service.chat.actions.JenkinsService", return_value=instance), \
            patch("argus.backend.service.chat.tools.JenkinsService", return_value=instance):
        yield instance


@pytest.fixture
async def seeded(release_manager_service):
    return await seed_entity_release(release_manager_service)


@pytest.fixture
async def ctx(seeded, logged_in_user):
    return ToolContext(entity=await resolve_entity("release", seeded.release.id), user=logged_in_user, node=uuid1())


async def call(ctx, name: str, **arguments):
    return await run_tool(ctx, ToolCall("c1", name, json.dumps(arguments)))


def params_of(outcome, index: int = 0) -> dict:
    assert outcome.action is not None, outcome.content
    return outcome.action["proposal"]["tests"][index]["params"]


async def test_a_seed_picks_where_the_parameters_come_from(ctx, seeded, jenkins):
    test = seeded.tests[0].name

    last = params_of(await call(ctx, "execute_tests", tests=[test]))
    defaults = params_of(await call(ctx, "execute_tests", tests=[test], seed="defaults"))
    build = params_of(await call(ctx, "execute_tests", tests=[test], seed="build", build_number=7))

    assert (last["region"], last["scylla_version"]) == ("eu-west-1", "")
    assert (defaults["scylla_version"], defaults["scylla_repo"]) == ("master:latest", "")
    assert build["region"] == "us-east-1"
    jenkins.retrieve_job_parameters.assert_any_call(seeded.tests[0].build_system_id, 7, from_defaults=False)


@pytest.mark.parametrize("version", ["master:latest", "branch-2025.1:latest", "master:1234",
                                     "master:2025-11-01T10:00:00Z", "2025.1", "2025.1.0~rc1", "2025.1.0-rc2",
                                     "2026.2.0~dev-0.20260322.f51126483167", "relocatable",
                                     "relocatable:master:x86_64", "relocatable:branch-2025.1:aarch64"])
async def test_every_wizard_version_form_is_accepted(ctx, seeded, jenkins, version):
    params = params_of(await call(ctx, "execute_tests", tests=[seeded.tests[0].name],
                                  params={"scylla_version": version}))

    assert (params["scylla_version"], params["scylla_repo"]) == (version, "")


@pytest.mark.parametrize("overrides", [
    {"region": "us-east-2"}, {"region": "ca-central-1"}, {"backend": "docker"}, {"backend": "xcloud"},
    {"provision_type": "auto"}, {"scylla_version": "latest"},
    {"azure_image_db": "scylladb:scylla-enterprise:2025-1:2025.1.0"},
    {"oci_image_db": "resolve:platform:Oracle Linux:10"},
    {"scylla_ami_id": "resolve:ssm:/aws/service/marketplace/prod-abc/latest"},
    {"scylla_ami_id": "ami-0123456789abcdef0 ami-0fedcba9876543210"},
])
async def test_values_sct_accepts_beyond_the_wizard_lists_pass(ctx, seeded, jenkins, overrides):
    outcome = await call(ctx, "execute_tests", tests=[seeded.tests[0].name], params=overrides)

    assert not outcome.error, outcome.content


async def test_overrides_follow_the_wizard(ctx, seeded, jenkins):
    params = params_of(await call(ctx, "execute_tests", tests=[seeded.tests[0].name],
                                  params={"scylla_version": "2025.1.0", "backend": "gce"}))

    assert params["scylla_repo"] == ""
    assert params["gce_datacenter"] == "us-east1"
    assert params["email_recipients"] == "qa@scylladb.com"


@pytest.mark.parametrize(("overrides", "reason"), [
    ({"azure_image_db": "not an image"}, "azure_image_db must be"),
    ({"scylla_ami_id": "not-an-ami"}, "scylla_ami_id must be"),
    ({"scylla_version": "master"}, "branch:latest"),
    ({"byo_scylla_repo": "git@github.com:someone/scylla.git", "byo_scylla_branch": "gone"}, "not found"),
])
async def test_a_value_the_wizard_refuses_rejects_the_test(ctx, seeded, jenkins, overrides, reason):
    with patch("argus.backend.service.chat.sct_params.GithubService") as github:
        github.return_value.validate_repo = AsyncMock(return_value=(False, "Branch 'gone' not found"))
        outcome = await call(ctx, "execute_tests", tests=[seeded.tests[0].name], params=overrides)

    assert outcome.error and reason in outcome.content


async def test_per_test_overrides_win(ctx, seeded, jenkins):
    outcome = await call(ctx, "execute_tests", tests=[seeded.tests[0].name, seeded.tests[1].name],
                         params={"provision_type": "on_demand"},
                         per_test={seeded.tests[1].name: {"provision_type": "spot_fleet"}})

    by_test = {test["name"]: test["params"]["provision_type"] for test in outcome.action["proposal"]["tests"]}
    assert by_test == {seeded.tests[0].name: "on_demand", seeded.tests[1].name: "spot_fleet"}


async def test_job_params_come_in_the_wizard_groups(ctx, seeded, jenkins):
    outcome = await call(ctx, "get_job_params", test=seeded.tests[0].name)

    groups = json.loads(outcome.content)["groups"]
    environment = {field["name"]: field for field in groups["environment"]}
    assert "gce" in environment["backend"]["suggestions"] and "choices" not in environment["backend"]
    assert environment["region"]["suggestions"][0] == "eu-west-1"
    assert environment["provision_type"]["description"] == "How the instances are provisioned"
    assert groups["post_test"][0]["choices"] == ["destroy", "keep", "keep-on-failure"]
    version = next(field for field in groups["scylla"] if field["name"] == "scylla_version")
    assert "master:latest" in version["format"]


async def test_a_dry_run_lists_the_labelled_tests(ctx, seeded, jenkins, logged_in_user):
    payload = CreatePlanPayload(
        name=unique("plan"), description="", owner=logged_in_user.id, participants=[], target_version="2037.1",
        release_id=seeded.release.id, tests=[seeded.tests[0].id], groups=[], assignments={},
        options={str(seeded.tests[0].id): {"labels": ["week1"]}})
    plan = await PlanningService().create_plan(payload, logged_in_user)

    outcome = await call(ctx, "execute_plan_tests", plan=plan.name, labels=["week1"], dry_run=True)

    assert outcome.action is None
    assert json.loads(outcome.content)["tests"] == [f"{seeded.group.name}/{seeded.tests[0].name}"]


async def start_card(seeded, chat_model, logged_in_user):
    entity = await resolve_entity("release", seeded.release.id)
    service = ChatService(ChatHub())
    chat_model.turns = [tool_turn(("execute_tests", {"tests": [seeded.tests[0].name]})), text_turn("Confirm it")]
    await service.send(entity, "start it", logged_in_user)
    await chat_tasks.drain()
    _, nodes = await ChatHistoryService(entity).read()
    return entity, service, next(node for node in nodes if node.role == "action")


async def test_a_pending_card_is_adjusted_until_it_is_confirmed(seeded, jenkins, chat_model, logged_in_user):
    entity, service, card = await start_card(seeded, chat_model, logged_in_user)
    ctx = ToolContext(entity=entity, user=logged_in_user, node=uuid1())

    adjusted = await call(ctx, "adjust_run_params", set={"region": "us-west-2"})
    _, nodes = await ChatHistoryService(entity).read()
    stored = json.loads(next(node for node in nodes if node.node == card.node).action)
    await service.confirm(entity, card.node, logged_in_user)
    await chat_tasks.drain()
    late = await call(ctx, "adjust_run_params", card=str(card.node), set={"region": "eu-west-2"})

    assert not adjusted.error, adjusted.content
    assert stored["proposal"]["tests"][0]["params"]["region"] == "us-west-2"
    assert stored["proposal"]["tests"][0]["overrides"] == {"region": "us-west-2"}
    assert jenkins.build_job.call_args.kwargs["params"]["region"] == "us-west-2"
    assert late.error and "done" in late.content


async def test_the_card_route_checks_the_edited_parameters(seeded, jenkins, chat_model, logged_in_user,
                                                           chat_client):
    entity, _, card = await start_card(seeded, chat_model, logged_in_user)
    route = f"/api/v1/chat/release/{entity.id}/actions/{card.node}/params"
    test_id = str(seeded.tests[0].id)

    refused = chat_client.post(route, json={"tests": {test_id: {"post_behavior_db_nodes": "explode"}}}).json()
    accepted = chat_client.post(route, json={"tests": {test_id: {"post_behavior_db_nodes": "keep"}}}).json()

    assert refused["status"] == "error"
    assert accepted["status"] == "ok"
    assert accepted["response"]["action"]["proposal"]["tests"][0]["params"]["post_behavior_db_nodes"] == "keep"
    with pytest.raises(ChatActionError):
        await ChatService().adjust(entity, card.node, {test_id: {"scylla_ami_id": "not-an-ami"}})
