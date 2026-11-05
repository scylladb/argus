import json
from uuid import uuid1

import pytest

from argus.backend.service.chat import tasks as chat_tasks
from argus.backend.service.chat.entity import resolve_entity
from argus.backend.service.chat.history import ChatHistoryService
from argus.backend.service.chat.hub import ChatHub
from argus.backend.service.chat.llm import ToolCall
from argus.backend.service.chat.service import ChatService
from argus.backend.service.chat.tools import ToolContext, run_tool
from argus.backend.service.planner_service import CreatePlanPayload, PlanDiffPayload, PlanningService
from argus.backend.tests.chat.helpers import seed_entity_release, text_turn, tool_turn
from argus.backend.tests.release_summary.helpers import unique

pytestmark = pytest.mark.docker_required


@pytest.fixture
async def seeded(release_manager_service):
    return await seed_entity_release(release_manager_service)


@pytest.fixture
async def plan(seeded, logged_in_user):
    payload = CreatePlanPayload(
        name=unique("plan"), description="", owner=logged_in_user.id, participants=[], target_version="2037.1",
        release_id=seeded.release.id, tests=[seeded.tests[0].id], groups=[], assignments={},
        options={str(seeded.tests[0].id): {"labels": ["week1", "sanity"]}})
    return await PlanningService().create_plan(payload, logged_in_user)


@pytest.fixture
async def ctx(seeded, logged_in_user):
    return ToolContext(entity=await resolve_entity("release", seeded.release.id), user=logged_in_user, node=uuid1())


async def call(ctx, name: str, **arguments):
    return await run_tool(ctx, ToolCall("c1", name, json.dumps(arguments)))


async def test_labels_name_the_entities_that_carry_them(ctx, seeded, plan):
    outcome = await call(ctx, "get_plan_labels", plan=plan.name)

    labels = {entry["label"]: entry["entities"] for entry in json.loads(outcome.content)["labels"]}
    assert set(labels) == {"week1", "sanity"}
    assert labels["week1"] == [{"test": f"{seeded.group.name}/{seeded.tests[0].name}", "enabled": True}]


async def test_an_edit_follows_the_command_line_rules(ctx, seeded, plan, chat_people):
    alice = chat_people[0]
    first, second = (str(test.id) for test in seeded.tests)

    outcome = await call(ctx, "edit_plan", plan=plan.name, add_labels={seeded.tests[1].name: ["week1"]},
                         remove_labels={seeded.tests[0].name: ["SANITY"]},
                         assign={seeded.tests[1].name: alice.username}, target_version="2037.2")

    diff = outcome.action["proposal"]["diff"]
    assert diff["tests_add"] == [second]
    assert diff["options_set"] == {second: {"labels": ["week1"]}, first: {"labels": ["week1"]}}
    assert diff["assignee_mapping_set"] == {second: str(alice.id)}
    assert diff["participants_add"] == [str(alice.id)]
    assert diff["target_version"] == "2037.2"
    assert any(line.startswith("assign") and alice.username in line for line in outcome.action["proposal"]["summary"])


async def test_removing_the_last_label_removes_the_options(ctx, seeded, plan):
    outcome = await call(ctx, "edit_plan", plan=plan.name,
                         remove_labels={seeded.tests[0].name: ["week1", "sanity"]})

    assert outcome.action["proposal"]["diff"]["options_remove"] == [str(seeded.tests[0].id)]


async def test_a_user_is_found_by_full_name(ctx, seeded, plan, chat_people):
    outcome = await call(ctx, "edit_plan", plan=plan.name, assign={seeded.tests[0].name: chat_people[1].full_name})

    assert outcome.action["proposal"]["diff"]["assignee_mapping_set"] == {
        str(seeded.tests[0].id): str(chat_people[1].id)}


async def test_an_edit_that_empties_the_plan_is_refused(ctx, seeded, plan):
    outcome = await call(ctx, "edit_plan", plan=plan.name, remove_tests=[seeded.tests[0].name])

    assert outcome.error and "without tests" in outcome.content


async def edit_card(seeded, plan, chat_model, user, arguments: dict):
    entity = await resolve_entity("release", seeded.release.id)
    service = ChatService(ChatHub())
    chat_model.turns = [tool_turn(("edit_plan", {"plan": plan.name, **arguments})), text_turn("Apply the card")]
    await service.send(entity, "edit the plan", user)
    await chat_tasks.drain()
    _, nodes = await ChatHistoryService(entity).read()
    return entity, service, next(node for node in nodes if node.role == "action")


async def confirmed(entity, service, card, user) -> dict:
    await service.confirm(entity, card.node, user)
    await chat_tasks.drain()
    _, nodes = await ChatHistoryService(entity).read()
    return json.loads(next(node for node in nodes if node.node == card.node).action)


async def test_confirming_applies_the_edit(seeded, plan, chat_model, logged_in_user, chat_people):
    entity, service, card = await edit_card(seeded, plan, chat_model, logged_in_user,
                                            {"assign": {seeded.tests[1].name: chat_people[0].username},
                                             "add_labels": {seeded.tests[1].name: ["week2"]}})

    action = await confirmed(entity, service, card, logged_in_user)
    stored = await PlanningService().get_plan(plan.id)

    assert action["results"] == [{"plan": plan.name, "error": None}]
    assert seeded.tests[1].id in stored.tests
    assert stored.assignee_mapping[seeded.tests[1].id] == chat_people[0].id
    assert chat_people[0].id in stored.participants
    assert json.loads(stored.options)[str(seeded.tests[1].id)] == {"labels": ["week2"]}


async def test_a_plan_changed_after_the_proposal_is_not_edited(seeded, plan, chat_model, logged_in_user):
    entity, service, card = await edit_card(seeded, plan, chat_model, logged_in_user, {"target_version": "2037.9"})
    await PlanningService().update_plan(PlanDiffPayload(id=str(plan.id), description="changed meanwhile"),
                                        logged_in_user)

    action = await confirmed(entity, service, card, logged_in_user)

    assert "changed since" in action["results"][0]["error"]
    assert (await PlanningService().get_plan(plan.id)).target_version == "2037.1"
