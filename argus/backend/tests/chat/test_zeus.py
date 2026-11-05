import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid1, uuid4

import httpx
import pytest

from argus.backend.service.chat import tasks as chat_tasks
from argus.backend.service.chat.actions import refresh_due
from argus.backend.service.chat.entity import resolve_entity
from argus.backend.service.chat.history import ChatHistoryService
from argus.backend.service.chat.hub import ChatHub
from argus.backend.service.chat.llm import ToolCall
from argus.backend.service.chat.service import ChatService
from argus.backend.service.chat.tools import ToolContext, run_tool, tool_specs
from argus.backend.service.zeus_client import ZeusClient, ZeusError
from argus.backend.tests.chat.helpers import seed_entity_release, seed_view, text_turn, tool_turn
from argus.backend.tests.release_summary.helpers import submit_run
from argus.backend.util.config import Config

pytestmark = pytest.mark.docker_required

ZEUS = {"ZEUS_SCHEMA": "https", "ZEUS_HOST": "zeus.test", "ZEUS_TOKEN": "zeus-secret"}


class FakeZeus:
    """Stands in for ZeusClient: queues tasks, then answers their status from ``tasks``."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.tasks: dict[str, dict] = {}
        self.status_calls = 0
        self.refuse: set[int] = set()
        self.unreachable = False

    def configured(self) -> bool:
        return True

    async def investigate(self, prompt: str) -> str:
        index = len(self.prompts)
        self.prompts.append(prompt)
        if index in self.refuse:
            raise ZeusError("Zeus answered 503: zeus is waiting for llm_api")
        task_id = f"task-{index}"
        self.tasks[task_id] = {"task_id": task_id, "status": "queued", "prompt": prompt, "response": None,
                               "error": None, "created_at": "2030-01-01T00:00:00", "started_at": None,
                               "completed_at": None}
        return task_id

    async def status(self, task_id: str) -> dict:
        self.status_calls += 1
        if self.unreachable:
            raise ZeusError("Zeus could not be reached")
        return self.tasks[task_id]


@pytest.fixture
def zeus(monkeypatch) -> FakeZeus:
    fake = FakeZeus()
    monkeypatch.setattr("argus.backend.service.chat.actions.ZeusClient", lambda: fake)
    monkeypatch.setattr("argus.backend.service.chat.tools.ZeusClient", lambda: fake)
    return fake


@pytest.fixture
async def seeded(release_manager_service, client_service):
    seeded = await seed_entity_release(release_manager_service)
    seeded.runs = [await submit_run(client_service, test, "2038.1.0~rc4", "failed") for test in seeded.tests]
    return seeded


@pytest.fixture
async def ctx(seeded, logged_in_user):
    return ToolContext(entity=await resolve_entity("release", seeded.release.id), user=logged_in_user, node=uuid1())


async def call(ctx, name: str, **arguments):
    return await run_tool(ctx, ToolCall("c1", name, json.dumps(arguments, default=str)))


def zeus_transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def test_the_client_queues_and_reads_a_task(monkeypatch):
    for key, value in ZEUS.items():
        monkeypatch.setitem(Config.CONFIG, key, value)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url), request.headers["authorization"]))
        if request.method == "POST":
            assert json.loads(request.content) == {"prompt": "Investigate run X"}
            return httpx.Response(202, json={"task_id": "t1", "status": "queued"})
        return httpx.Response(200, json={"task_id": "t1", "status": "completed", "response": "Root cause: OOM"})

    client = ZeusClient(transport=zeus_transport(handler))

    assert client.configured()
    assert await client.investigate("Investigate run X") == "t1"
    assert (await client.status("t1"))["response"] == "Root cause: OOM"
    assert seen == [("POST", "https://zeus.test/investigate", "Bearer zeus-secret"),
                    ("GET", "https://zeus.test/investigate/t1", "Bearer zeus-secret")]


async def test_the_client_reports_zeus_refusing_work(monkeypatch):
    for key, value in ZEUS.items():
        monkeypatch.setitem(Config.CONFIG, key, value)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "zeus is waiting for llm_api"}, headers={"Retry-After": "60"})

    with pytest.raises(ZeusError, match="waiting for llm_api"):
        await ZeusClient(transport=zeus_transport(handler)).investigate("x")


def test_the_zeus_tools_are_hidden_without_zeus(monkeypatch):
    for key in ZEUS:
        monkeypatch.setitem(Config.CONFIG, key, None)

    names = {spec.name for spec in tool_specs()}

    assert "investigate_runs" not in names
    assert "get_investigation" in names


def test_the_zeus_tools_are_offered_with_zeus(monkeypatch):
    for key, value in ZEUS.items():
        monkeypatch.setitem(Config.CONFIG, key, value)

    assert {"investigate_runs", "get_investigation"} <= {spec.name for spec in tool_specs()}


async def test_a_proposal_names_each_run_and_carries_the_prompt(ctx, seeded, zeus, logged_in_user):
    outcome = await call(ctx, "investigate_runs", runs=[str(run) for run in seeded.runs],
                         question="Focus on the upgrade step.")

    action = outcome.action
    assert action["kind"] == "zeus_investigation"
    assert [run["run_id"] for run in action["proposal"]["runs"]] == [str(run) for run in seeded.runs]
    prompt = action["proposal"]["runs"][0]["prompt"]
    assert str(seeded.runs[0]) in prompt
    assert f"{seeded.group.name}/{seeded.tests[0].name}" in prompt and "failed" in prompt
    assert "2038.1.0~rc4" in prompt and seeded.release.name in prompt
    assert "Test User" in prompt and prompt.endswith("Focus on the upgrade step.")
    assert "confirm" in outcome.content.lower()
    assert zeus.prompts == []


async def test_runs_outside_the_chat_and_too_many_runs_are_refused(seeded, zeus, logged_in_user):
    view = await seed_view(logged_in_user, [seeded.tests[1]])
    ctx = ToolContext(entity=await resolve_entity("view", view.id), user=logged_in_user, node=uuid1())

    outside = await call(ctx, "investigate_runs", runs=[str(seeded.runs[0])])
    too_many = await call(ctx, "investigate_runs", runs=[str(uuid4()) for _ in range(6)])

    assert outside.error and "outside" in outside.content
    assert too_many.error


async def card_from_chat(seeded, chat_model, logged_in_user, arguments: dict):
    entity = await resolve_entity("release", seeded.release.id)
    service = ChatService(ChatHub())
    chat_model.turns = [tool_turn(("investigate_runs", arguments)), text_turn("Confirm the card")]
    await service.send(entity, "investigate them", logged_in_user)
    await chat_tasks.drain()
    _, nodes = await ChatHistoryService(entity).read()
    return entity, service, next(node for node in nodes if node.role == "action")


async def read_card(entity, node: UUID) -> dict:
    _, nodes = await ChatHistoryService(entity).read()
    card = next(candidate for candidate in nodes if candidate.node == node)
    return json.loads(card.action) | {"state": card.action_state}


async def test_confirming_queues_each_run_once_and_records_a_refusal(seeded, zeus, chat_model, logged_in_user,
                                                                     monkeypatch):
    for key, value in ZEUS.items():
        monkeypatch.setitem(Config.CONFIG, key, value)
    zeus.refuse = {1}
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user,
                                                 {"runs": [str(run) for run in seeded.runs]})

    await service.confirm(entity, card.node, logged_in_user)
    await chat_tasks.drain()

    action = await read_card(entity, card.node)
    assert action["state"] == "done"
    assert len(zeus.prompts) == 2
    first, second = action["results"]
    assert (first["run_id"], first["task_id"], first["status"]) == (str(seeded.runs[0]), "task-0", "queued")
    assert (second["task_id"], second["status"]) == (None, "failed")
    assert "waiting for llm_api" in second["error"]


async def test_a_refresh_reads_zeus_at_most_every_15_seconds(seeded, zeus, chat_model, logged_in_user, monkeypatch):
    for key, value in ZEUS.items():
        monkeypatch.setitem(Config.CONFIG, key, value)
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user,
                                                 {"runs": [str(seeded.runs[0])]})
    await service.confirm(entity, card.node, logged_in_user)
    await chat_tasks.drain()
    zeus.tasks["task-0"].update(status="completed", response="Root cause: the AMI never booted.",
                                completed_at="2030-01-01T00:20:00")

    throttled = await service.refresh(entity, card.node)
    monkeypatch.setattr("argus.backend.service.chat.actions.ZEUS_REFRESH_SECONDS", 0)
    refreshed = await service.refresh(entity, card.node)
    again = await service.refresh(entity, card.node)

    assert throttled["action"]["results"][0]["status"] == "queued"
    assert refreshed["action"]["results"][0]["status"] == "completed"
    assert refreshed["action"]["results"][0]["response"] == "Root cause: the AMI never booted."
    assert again["action"]["results"][0]["status"] == "completed"
    assert zeus.status_calls == 1


async def test_an_unreachable_zeus_keeps_the_last_status(seeded, zeus, chat_model, logged_in_user, monkeypatch):
    for key, value in ZEUS.items():
        monkeypatch.setitem(Config.CONFIG, key, value)
    monkeypatch.setattr("argus.backend.service.chat.actions.ZEUS_REFRESH_SECONDS", 0)
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user,
                                                 {"runs": [str(seeded.runs[0])]})
    await service.confirm(entity, card.node, logged_in_user)
    await chat_tasks.drain()
    zeus.unreachable = True

    refreshed = await service.refresh(entity, card.node)

    result = refreshed["action"]["results"][0]
    assert result["status"] == "queued"
    assert "could not be reached" in result["refresh_error"]


async def test_get_investigation_returns_the_reports(seeded, zeus, chat_model, logged_in_user, monkeypatch):
    for key, value in ZEUS.items():
        monkeypatch.setitem(Config.CONFIG, key, value)
    monkeypatch.setattr("argus.backend.service.chat.actions.ZEUS_REFRESH_SECONDS", 0)
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user,
                                                 {"runs": [str(seeded.runs[0])]})
    await service.confirm(entity, card.node, logged_in_user)
    await chat_tasks.drain()
    zeus.tasks["task-0"].update(status="completed", response="Root cause: OOM on node 2.")
    ctx = ToolContext(entity=entity, user=logged_in_user, node=uuid1())

    outcome = await call(ctx, "get_investigation", run=str(seeded.runs[0]))
    none = await call(ctx, "get_investigation", run=str(seeded.runs[1]))

    [report] = json.loads(outcome.content)["investigations"]
    assert (report["status"], report["response"]) == ("completed", "Root cause: OOM on node 2.")
    assert none.error and "No Zeus report" in none.content


async def test_the_next_prompt_carries_the_report(seeded, zeus, chat_model, logged_in_user, monkeypatch):
    for key, value in ZEUS.items():
        monkeypatch.setitem(Config.CONFIG, key, value)
    monkeypatch.setattr("argus.backend.service.chat.actions.ZEUS_REFRESH_SECONDS", 0)
    entity, service, card = await card_from_chat(seeded, chat_model, logged_in_user,
                                                 {"runs": [str(seeded.runs[0])]})
    await service.confirm(entity, card.node, logged_in_user)
    await chat_tasks.drain()
    zeus.tasks["task-0"].update(status="completed", response="Root cause: OOM on node 2.")
    await service.refresh(entity, card.node)
    chat_model.turns = [text_turn("It ran out of memory.")]

    await service.send(entity, "what did Zeus find?", logged_in_user)
    await chat_tasks.drain()

    last = chat_model.requests[-1].messages[-1].content
    assert "queued Zeus investigations" in last and "Root cause: OOM on node 2." in last
    assert last.endswith("what did Zeus find?")


def test_refresh_is_throttled_by_the_stamp():
    now = datetime.now(UTC)
    assert refresh_due(None, now)
    assert not refresh_due((now - timedelta(seconds=5)).isoformat(), now)
    assert refresh_due((now - timedelta(seconds=20)).isoformat(), now)
