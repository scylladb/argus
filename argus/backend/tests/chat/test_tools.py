import json
import uuid
from uuid import UUID, uuid1

import pytest

from argus.backend.service.chat.entity import resolve_entity
from argus.backend.service.chat.llm import ToolCall
from argus.backend.service.chat.memory import ChatMemoryService
from argus.backend.service.chat.tools import TOOLS, ToolContext, run_tool, tool_specs
from argus.backend.service.planner_service import CreatePlanPayload, PlanningService
from argus.backend.tests.chat.helpers import seed_entity_release, seed_view
from argus.backend.tests.release_summary.helpers import submit_run, unique
from argus.common.sct_types import RawEventPayload

pytestmark = pytest.mark.docker_required


async def call(ctx: ToolContext, name: str, **arguments):
    outcome = await run_tool(ctx, ToolCall("c1", name, json.dumps(arguments)))
    return outcome, (json.loads(outcome.content) if not outcome.error else outcome.content)


@pytest.fixture
async def seeded(release_manager_service, client_service):
    seeded = await seed_entity_release(release_manager_service)
    seeded.runs = [
        await submit_run(client_service, seeded.tests[0], "2035.1.0~rc1", "failed"),
        await submit_run(client_service, seeded.tests[1], "2035.1.0~rc1", "passed"),
    ]
    return seeded


@pytest.fixture
async def release_ctx(seeded, logged_in_user):
    return ToolContext(entity=await resolve_entity("release", seeded.release.id), user=logged_in_user, node=uuid1())


def test_every_tool_has_an_object_schema():
    specs = {spec.name: spec for spec in tool_specs()}

    assert set(specs) == {name for name, entry in TOOLS.items() if entry.available()}
    assert {"get_summary", "read_release", "read_view", "get_runs", "read_run", "get_plan", "read_memory",
            "write_memory"} <= set(specs)
    assert all(spec.parameters["type"] == "object" for spec in specs.values())


async def test_get_summary_gives_counts_and_filtered_tests(release_ctx, seeded):
    _, summary = await call(release_ctx, "get_summary", version="2035.1.0~rc1", statuses=["failed"])

    family = summary["releases"][0]["families"][0]
    assert family["family"] == "2035.1.0"
    assert family["rollup"]["failed"] == 1 and family["rollup"]["passed"] == 1
    version = family["versions"][0]
    assert version["version"] == "2035.1.0~rc1"
    assert [test["test"] for test in version["tests"]] == [seeded.tests[0].name]


async def test_a_single_string_is_accepted_where_a_list_is_expected(release_ctx, seeded):
    outcome, summary = await call(release_ctx, "get_summary", version="2035.1.0~rc1", statuses="failed")

    assert not outcome.error
    assert [test["test"] for test in summary["releases"][0]["families"][0]["versions"][0]["tests"]] == [
        seeded.tests[0].name]


async def test_read_release_lists_tests_with_their_job(release_ctx, seeded):
    _, release = await call(release_ctx, "read_release")

    tests = {test["name"]: test for test in release["tests"]}
    assert release["name"] == seeded.release.name
    assert tests[seeded.tests[0].name]["build_system_id"] == seeded.tests[0].build_system_id
    assert tests[seeded.tests[0].name]["group"] == seeded.group.name


async def test_get_runs_and_read_run(release_ctx, seeded):
    _, runs = await call(release_ctx, "get_runs", test=seeded.tests[0].name)
    _, run = await call(release_ctx, "read_run", run=str(seeded.runs[0]))

    assert [entry["id"] for entry in runs["runs"]] == [str(seeded.runs[0])]
    assert runs["runs"][0]["status"] == "failed"
    assert (run["id"], run["status"], run["test"]) == (str(seeded.runs[0]), "failed", seeded.tests[0].name)
    assert run["issues"] == [] and run["comments"] == []


async def test_a_view_cannot_read_a_run_outside_its_tests(seeded, release_manager_service, client_service,
                                                          logged_in_user):
    view = await seed_view(logged_in_user, [seeded.tests[1]])
    ctx = ToolContext(entity=await resolve_entity("view", view.id), user=logged_in_user, node=uuid1())

    outcome, message = await call(ctx, "read_run", run=str(seeded.runs[0]))
    _, view_info = await call(ctx, "read_view")

    assert outcome.error and "outside" in message
    assert view_info["name"] == view.display_name
    assert view_info["releases"] == [seeded.release.name]
    assert view_info["tests"] == [f"{seeded.group.name}/{seeded.tests[1].name}"]


async def test_get_plan_shows_labels(release_ctx, seeded, logged_in_user):
    payload = CreatePlanPayload(
        name=unique("plan"), description="", owner=logged_in_user.id, participants=[], target_version="2035.1",
        release_id=seeded.release.id, tests=[test.id for test in seeded.tests], groups=[], assignments={},
        options={str(seeded.tests[0].id): {"labels": ["week1", "gce"]}})
    plan = await PlanningService().create_plan(payload, logged_in_user)

    _, plans = await call(release_ctx, "get_plan")

    entry = next(entry for entry in plans["plans"] if entry["id"] == str(plan.id))
    assert entry["target_version"] == "2035.1"
    assert {test["name"]: test["labels"] for test in entry["tests"]}[seeded.tests[0].name] == ["week1", "gce"]


async def test_write_memory_records_the_chat_as_its_source(release_ctx):
    _, written = await call(release_ctx, "write_memory", op="add", content="We run on GCE", kind="note")
    _, read = await call(release_ctx, "read_memory", query="gce")
    _, deleted = await call(release_ctx, "write_memory", op="delete", memory_id=written["id"])

    history = await ChatMemoryService().history(release_ctx.entity)
    assert read["memories"][0]["content"] == "We run on GCE"
    assert deleted["deleted"] == written["id"]
    assert all(entry["source"] == "chat" and entry["source_node"] == release_ctx.node for entry in history)


async def test_bad_calls_come_back_as_errors(release_ctx):
    unknown, unknown_message = await call(release_ctx, "launch_rockets")
    bad_args, bad_message = await call(release_ctx, "get_runs", limit=5)
    broken = await run_tool(release_ctx, ToolCall("c1", "get_runs", "{not json"))
    missing, missing_message = await call(release_ctx, "read_run", run=str(uuid.uuid4()))

    assert unknown.error and "launch_rockets" in unknown_message
    assert bad_args.error and "test" in bad_message
    assert broken.error
    assert missing.error and "not found" in missing_message.lower()


async def test_get_users_names_people_and_marks_unknown_ids(release_ctx, chat_people):
    alice, bob = chat_people
    missing = uuid.uuid4()

    _, found = await call(release_ctx, "get_users", user_ids=[str(alice.id), str(bob.id), str(missing)])

    by_id = {person["id"]: person for person in found["users"]}
    assert by_id[str(alice.id)] == {"id": str(alice.id), "username": alice.username, "name": "Alice Smith"}
    assert by_id[str(missing)] == {"id": str(missing), "unknown": True}


async def test_get_assignees_follows_the_plans_and_the_test(release_ctx, seeded, chat_people, logged_in_user,
                                                           release_manager_service):
    alice, bob = chat_people
    payload = CreatePlanPayload(
        name=unique("plan"), description="", owner=logged_in_user.id, participants=[alice.id],
        target_version="2035.1", release_id=seeded.release.id, tests=[seeded.tests[1].id], groups=[seeded.group.id],
        assignments={seeded.group.id: alice.id})
    await PlanningService().create_plan(payload, logged_in_user)

    _, assignees = await call(release_ctx, "get_assignees", tests=[seeded.tests[0].name])

    [entry] = assignees["tests"]
    assert entry["test"] == f"{seeded.group.name}/{seeded.tests[0].name}"
    assert [(plan["assignee"]["name"], plan["target_version"]) for plan in entry["plans"]] == [
        ("Alice Smith", "2035.1")]
    assert entry["last_run"]["status"] == "failed"


async def test_run_tools_name_the_assignee(release_ctx, seeded, chat_people, testrun_service, asgi_app):
    alice, bob = chat_people
    await testrun_service.change_run_assignee(seeded.tests[0].id, seeded.runs[0], alice.id, bob)

    _, run = await call(release_ctx, "read_run", run=str(seeded.runs[0]))
    _, runs = await call(release_ctx, "get_runs", test=seeded.tests[0].name)

    assert run["assignee"] == {"id": str(alice.id), "username": alice.username, "name": "Alice Smith"}
    assert runs["runs"][0]["assignee"]["name"] == "Alice Smith"


def sct_event(run_id: UUID, severity: str, message: str, offset: int) -> RawEventPayload:
    return RawEventPayload(run_id=str(run_id), severity=severity, ts=1_900_000_000 + offset, message=message,
                           event_type="DatabaseLogEvent", received_timestamp=None, nemesis_name="disrupt_kill",
                           duration=None, node="node-1", target_node=None, known_issue=None, nemesis_status=None)


async def test_run_events_list_the_errors_of_an_sct_run(release_ctx, seeded, sct_service):
    run_id = seeded.runs[0]
    await sct_service.submit_events(run_id, [
        sct_event(run_id, "ERROR", "Reactor stalled for 250 ms", 1),
        sct_event(run_id, "CRITICAL", "Node node-1 lost its data", 2),
        sct_event(run_id, "NORMAL", "Nemesis started", 3),
    ])

    _, events = await call(release_ctx, "get_run_events", run=str(run_id))
    _, normal = await call(release_ctx, "get_run_events", run=str(run_id), severities="NORMAL")
    _, run = await call(release_ctx, "read_run", run=str(run_id))

    assert [(event["severity"], event["message"]) for event in events["events"]] == [
        ("ERROR", "Reactor stalled for 250 ms"), ("CRITICAL", "Node node-1 lost its data")]
    assert events["events"][0]["nemesis"] == "disrupt_kill" and events["events"][0]["node"] == "node-1"
    assert [event["message"] for event in normal["events"]] == ["Nemesis started"]
    assert run["events"]["counts"] == {"CRITICAL": 1, "ERROR": 1}
    assert [event["message"] for event in run["events"]["first"]] == [
        "Reactor stalled for 250 ms", "Node node-1 lost its data"]


async def test_run_activity_names_who_did_what(release_ctx, seeded, chat_people, testrun_service, asgi_app):
    alice, bob = chat_people
    await testrun_service.change_run_assignee(seeded.tests[0].id, seeded.runs[0], alice.id, bob)

    _, activity = await call(release_ctx, "get_run_events", run=str(seeded.runs[0]), kind="activity")

    [event] = [event for event in activity["events"] if event["kind"] == "ARGUS_ASSIGNEE_CHANGE"]
    assert event["by"]["name"] == "Bob Jones"


async def test_get_runs_shows_and_filters_the_version(release_ctx, seeded, client_service):
    await submit_run(client_service, seeded.tests[0], "2035.1.0", "passed")

    _, every = await call(release_ctx, "get_runs", test=seeded.tests[0].name)
    _, rc1 = await call(release_ctx, "get_runs", test=seeded.tests[0].name, version="2035.1.0~rc1")

    assert [(run["version"], run["status"]) for run in every["runs"]] == [("2035.1.0", "passed"),
                                                                          ("2035.1.0~rc1", "failed")]
    assert [(run["version"], run["status"]) for run in rc1["runs"]] == [("2035.1.0~rc1", "failed")]
