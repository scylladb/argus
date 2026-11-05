import time
import uuid

import pytest
from starlette.testclient import TestClient

from argus.backend.controller.chat_api import event_stream
from argus.backend.service.chat import tasks as chat_tasks
from argus.backend.service.chat.entity import resolve_entity
from argus.backend.service.chat.hub import ChatHub
from argus.backend.service.chat.service import ChatService
from argus.backend.tests.chat.helpers import seed_entity_release, text_turn

pytestmark = pytest.mark.docker_required


def ok(response):
    body = response.json()
    assert body["status"] == "ok", body
    return body["response"]


def wait_idle(client: TestClient, base: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        conversation = ok(client.get(base))
        if conversation["busy"] is None:
            return conversation
        time.sleep(0.05)
    raise AssertionError("The chat stayed busy")


@pytest.fixture
async def base(release_manager_service) -> str:
    seeded = await seed_entity_release(release_manager_service)
    return f"/api/v1/chat/release/{seeded.release.id}"


async def test_a_question_is_queued_and_answered(chat_client: TestClient, base, chat_model):
    chat_model.turns = [text_turn("an answer")]

    started = ok(chat_client.post(f"{base}/messages", json={"content": "what failed?"}))
    conversation = wait_idle(chat_client, base)
    meta = ok(chat_client.get(f"{base}/meta"))

    assert started["user_node"]["content"] == "what failed?"
    assert started["assistant_node"]["status"] == "streaming"
    assert conversation["head"] == started["assistant_node"]["node"]
    assert [node["content"] for node in conversation["nodes"]] == ["what failed?", "an answer"]
    assert meta["configured"] is True and meta["messages"] == 1
    assert [scope["type"] for scope in conversation["scopes"]] == ["release"]
    assert meta["last"]["user_id"] == started["user_node"]["user_id"]


async def test_try_again_undo_and_head(chat_client: TestClient, base, chat_model):
    chat_model.turns = [text_turn("first"), text_turn("second")]
    started = ok(chat_client.post(f"{base}/messages", json={"content": "q"}))
    wait_idle(chat_client, base)
    ok(chat_client.post(f"{base}/regenerate"))
    wait_idle(chat_client, base)

    switched = ok(chat_client.post(f"{base}/head", json={"node": started["assistant_node"]["node"]}))
    undone = ok(chat_client.post(f"{base}/undo"))

    assert switched["head"] == started["assistant_node"]["node"]
    assert undone["head"] is None
    assert all(node["hidden"] for node in undone["nodes"])


async def test_an_empty_question_and_a_missing_model_are_errors(api_client: TestClient, base, clean_chat_config):
    empty = api_client.post(f"{base}/messages", json={"content": "  "}).json()
    unconfigured = api_client.post(f"{base}/messages", json={"content": "q"}).json()

    assert empty["status"] == "error"
    assert unconfigured["response"]["exception"] == "ChatNotConfiguredError"
    assert ok(api_client.get(f"{base}/meta"))["configured"] is False


def test_an_unknown_entity_is_refused(api_client: TestClient):
    body = api_client.get(f"/api/v1/chat/view/{uuid.uuid4()}").json()

    assert body["response"]["exception"] == "ChatEntityError"


async def test_the_event_stream_starts_with_a_snapshot(release_manager_service, chat_model, logged_in_user):
    seeded = await seed_entity_release(release_manager_service)
    entity = await resolve_entity("release", seeded.release.id)
    hub = ChatHub(poll_seconds=0.05)
    stream = event_stream(entity, logged_in_user, ChatService(hub), hub)

    retry = await anext(stream)
    first = await anext(stream)
    chat_model.turns = [text_turn("hi")]
    await ChatService(hub).send(entity, "hello", logged_in_user)
    frames = [await anext(stream) for _ in range(3)]
    await stream.aclose()
    await chat_tasks.drain()

    assert retry == "retry: 1000\n\n"
    assert first.startswith("data: ") and '"type": "snapshot"' in first
    assert all(frame.startswith("data: ") and frame.endswith("\n\n") for frame in frames)
    assert any('"type": "node"' in frame for frame in frames)


async def test_an_event_stream_ends_after_its_lifetime(release_manager_service, logged_in_user):
    seeded = await seed_entity_release(release_manager_service)
    entity = await resolve_entity("release", seeded.release.id)
    hub = ChatHub(poll_seconds=0.05, heartbeat_seconds=0.1, stream_seconds=0.35)

    frames = [frame async for frame in event_stream(entity, logged_in_user, ChatService(hub), hub)]

    assert frames[0].startswith("retry:")
    assert sum('"type": "heartbeat"' in frame for frame in frames) >= 2
    assert entity.id not in hub._subscriptions


async def test_close_all_ends_open_streams_at_once(release_manager_service, logged_in_user):
    seeded = await seed_entity_release(release_manager_service)
    entity = await resolve_entity("release", seeded.release.id)
    hub = ChatHub(poll_seconds=0.05, stream_seconds=30)
    stream = event_stream(entity, logged_in_user, ChatService(hub), hub)
    await anext(stream)
    await anext(stream)

    hub.close_all()
    rest = [frame async for frame in stream]

    assert all('"type": "close"' not in frame for frame in rest)
    assert entity.id not in hub._subscriptions


async def test_an_admin_wipes_the_chat_and_keeps_its_memories(chat_client: TestClient, base, chat_model):
    chat_model.turns = [text_turn("an answer")]
    ok(chat_client.post(f"{base}/messages", json={"content": "q"}))
    wait_idle(chat_client, base)
    ok(chat_client.post(f"{base}/memories", json={"content": "We run on GCE", "kind": "note"}))

    wiped = ok(chat_client.delete(base))

    assert (wiped["nodes"], wiped["head"]) == ([], None)
    assert ok(chat_client.get(f"{base}/meta"))["messages"] == 0
    assert [memory["content"] for memory in ok(chat_client.get(f"{base}/memories"))] == ["We run on GCE"]


@pytest.mark.usefixtures("normal_user_identity")
async def test_only_an_admin_wipes_a_chat(api_client: TestClient, base):
    assert api_client.delete(base).status_code == 403
