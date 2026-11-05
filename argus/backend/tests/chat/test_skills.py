import json
import time
from uuid import UUID, uuid1

import pytest
from starlette.testclient import TestClient

from argus.backend.service.chat.entity import resolve_entity
from argus.backend.service.chat.llm import ToolCall
from argus.backend.service.chat.prompt import TEMPLATE
from argus.backend.service.chat.tools import ToolContext, Toolbox, run_tool
from argus.backend.tests.chat.helpers import seed_entity_release, text_turn

pytestmark = pytest.mark.docker_required

API = "/admin/api/v1/chat"


def ok(response):
    body = response.json()
    assert body["status"] == "ok", body
    return body["response"]


def ask(client: TestClient, base: str, chat_model, question: str = "hello"):
    chat_model.turns = [text_turn("an answer")]
    ok(client.post(f"{base}/messages", json={"content": question}))
    deadline = time.monotonic() + 10
    while ok(client.get(base))["busy"] is not None and time.monotonic() < deadline:
        time.sleep(0.05)
    request = chat_model.requests[-1]
    return request.messages[0].content, [tool.name for tool in request.tools or []]


@pytest.fixture
async def base(release_manager_service) -> str:
    seeded = await seed_entity_release(release_manager_service)
    return f"/api/v1/chat/release/{seeded.release.id}"


async def test_skills_reach_the_prompt_by_their_mode(chat_client: TestClient, chat_model, base):
    _, before = ask(chat_client, base, chat_model)
    ok(chat_client.post(f"{API}/skill", json={"name": "conventions", "content": "Week1 runs on GCE.",
                                              "mode": "always"}))
    ok(chat_client.post(f"{API}/skill", json={"name": "triage", "description": "How to triage a failed run",
                                              "content": "Read the events first.", "mode": "on_demand"}))
    ok(chat_client.post(f"{API}/skill", json={"name": "hidden", "content": "Never shown.", "mode": "off"}))

    system, tools = ask(chat_client, base, chat_model)

    assert "load_skill" not in before and "load_skill" in tools
    assert "Week1 runs on GCE." in system
    assert "- triage: How to triage a failed run" in system and "Read the events first." not in system
    assert "Never shown." not in system and "hidden" not in system


async def test_load_skill_returns_an_on_demand_skill(chat_client: TestClient, chat_model, base, logged_in_user):
    ok(chat_client.post(f"{API}/skill", json={"name": "triage", "description": "Triage",
                                              "content": "Read the events first.", "mode": "on_demand"}))
    entity = await resolve_entity("release", UUID(base.rsplit("/", 1)[1]))
    ctx = ToolContext(entity=entity, user=logged_in_user, node=uuid1())

    loaded = await run_tool(ctx, ToolCall("c1", "load_skill", json.dumps({"name": "TRIAGE"})))
    hidden = await run_tool(ctx, ToolCall("c2", "load_skill", json.dumps({"name": "triage"})),
                            Toolbox(hidden=frozenset({"load_skill"})))

    assert json.loads(loaded.content) == {"skill": "triage", "content": "Read the events first."}
    assert hidden.error and "There is no tool load_skill" in hidden.content


@pytest.mark.parametrize(("template", "error"), [
    ("{tool_rules} {scope} {memories} {summary} {secret}", "Unknown placeholder {secret}"),
    ("{tool_rules} {scope} {summary}", "must keep {memories}"),
    ("{tool_rules} {scope} {memories} {summary} {", "stray brace"),
])
@pytest.mark.usefixtures("chat_model")
def test_a_broken_template_is_refused(chat_client: TestClient, template, error):
    body = chat_client.put(f"{API}/prompt", json={"template": template}).json()

    assert body["status"] == "error" and error in body["response"]["arguments"][0]


async def test_an_edited_template_answers_until_it_is_reset(chat_client: TestClient, chat_model, base):
    ok(chat_client.post(f"{API}/skill", json={"name": "conventions", "content": "Week1 runs on GCE.",
                                              "mode": "always"}))
    saved = ok(chat_client.put(f"{API}/prompt", json={
        "template": "You are a terse helper for {{argus}}.\n{tool_rules}\n{scope}\n{memories}\n{summary}"}))

    edited, _ = ask(chat_client, base, chat_model)
    reset = ok(chat_client.delete(f"{API}/prompt"))
    restored, _ = ask(chat_client, base, chat_model)

    assert saved["edited"] is True and "{memories}" in saved["template"]
    assert edited.startswith("You are a terse helper for {argus}.")
    assert edited.rstrip().endswith("Week1 runs on GCE.")
    assert reset["edited"] is False and reset["template"] == TEMPLATE
    assert restored.startswith("You are the assistant of Argus")


@pytest.mark.usefixtures("chat_model", "normal_user_identity")
def test_only_admins_edit_the_prompt_and_the_skills(chat_client: TestClient):
    assert chat_client.get(f"{API}/prompt").status_code == 403
    assert chat_client.post(f"{API}/skill", json={"name": "x", "content": "y"}).status_code == 403
