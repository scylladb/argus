import json
from uuid import uuid1

import pytest

from argus.backend.service.chat.entity import resolve_entity
from argus.backend.service.chat.llm import ToolCall
from argus.backend.service.chat.tools import TOOLS, ToolContext, run_tool
from argus.backend.tests.chat.helpers import seed_entity_release
from argus.backend.tests.release_summary.helpers import submit_run

pytestmark = pytest.mark.docker_required

REPORT_START = "## Investigation of rolling-upgrade\n\nRoot cause: the node ran out of memory during the upgrade."
REPORT_REST = "## nemesis: disrupt_rolling_restart\n\nThe restart hit the same OOM; see `scylla.log` on node-2."


@pytest.fixture
async def discussed(release_manager_service, client_service, testrun_service, chat_people, zeus_user, asgi_app):
    alice, _ = chat_people
    seeded = await seed_entity_release(release_manager_service)
    test = seeded.tests[0]
    run_id = await submit_run(client_service, test, "2040.1.0~rc1", "failed")
    for message, user in (("Looks like an OOM again?", alice), ("queued autoinvestigation", zeus_user),
                          (REPORT_START, zeus_user), (REPORT_REST, zeus_user)):
        await testrun_service.post_run_comment(test.id, run_id, message, {}, [], user)
    seeded.run = run_id
    return seeded


@pytest.fixture
async def ctx(discussed, logged_in_user):
    return ToolContext(entity=await resolve_entity("release", discussed.release.id), user=logged_in_user,
                       node=uuid1())


async def call(ctx, name: str, **arguments):
    return await run_tool(ctx, ToolCall("c1", name, json.dumps(arguments)))


async def test_the_discussion_names_its_authors_and_marks_zeus(ctx, discussed, chat_people, zeus_user):
    outcome = await call(ctx, "read_discussion", run=str(discussed.run))

    comments = json.loads(outcome.content)["comments"]
    assert sorted((comment["author"]["name"], comment["zeus"]) for comment in comments) == [
        ("Alice Smith", False), ("Zeus", True), ("Zeus", True), ("Zeus", True)]
    assert {comment["message"] for comment in comments if not comment["zeus"]} == {"Looks like an OOM again?"}


async def test_get_investigation_finds_the_report_in_the_discussion_and_shows_it(ctx, discussed):
    outcome = await call(ctx, "get_investigation", run=str(discussed.run))

    [report] = json.loads(outcome.content)["investigations"]
    assert report["source"] == "discussion"
    assert report["response"] == f"{REPORT_START}\n\n{REPORT_REST}"
    assert outcome.card_state == "done"
    card = outcome.action["proposal"]
    assert outcome.action["kind"] == "zeus_report"
    assert card["report"] == f"{REPORT_START}\n\n{REPORT_REST}"
    assert card["url"] == f"/test/{discussed.tests[0].build_system_id}/42"
    assert card["author"]["name"] == "Zeus"


async def test_no_report_is_said_plainly(release_manager_service, client_service, logged_in_user):
    seeded = await seed_entity_release(release_manager_service)
    run_id = await submit_run(client_service, seeded.tests[0], "2040.1.0~rc1", "failed")
    ctx = ToolContext(entity=await resolve_entity("release", seeded.release.id), user=logged_in_user, node=uuid1())

    outcome = await call(ctx, "get_investigation", run=str(run_id))

    assert outcome.error and "No Zeus report" in outcome.content


def test_reading_reports_needs_no_zeus_connection():
    assert TOOLS["get_investigation"].available()
    assert TOOLS["read_discussion"].available()
