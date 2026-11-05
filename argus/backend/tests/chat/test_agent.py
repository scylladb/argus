import asyncio

import pytest

from argus.backend.service.chat import tasks as chat_tasks
from argus.backend.service.chat.agent import MAX_MODEL_CALLS
from argus.backend.service.chat.config import ChatNotConfiguredError
from argus.backend.service.chat.entity import resolve_entity
from argus.backend.service.chat.history import ChatBusyError, ChatHistoryService, active_path
from argus.backend.service.chat.hub import ChatHub
from argus.backend.service.chat.llm import ChatModelError, Finished, TextDelta, Usage
from argus.backend.service.chat.memory import ChatMemoryService
from argus.backend.service.chat.service import ChatService
from argus.backend.tests.chat.helpers import seed_entity_release, text_turn, tool_turn
from argus.backend.tests.release_summary.helpers import submit_run

pytestmark = pytest.mark.docker_required


@pytest.fixture
async def entity(release_manager_service, client_service):
    seeded = await seed_entity_release(release_manager_service)
    await submit_run(client_service, seeded.tests[0], "2036.1.0~rc1", "failed")
    return await resolve_entity("release", seeded.release.id)


@pytest.fixture
def service() -> ChatService:
    return ChatService(ChatHub())


async def path_of(entity) -> list:
    state, nodes = await ChatHistoryService(entity).read()
    return active_path(nodes, state.head)


async def test_an_answer_is_streamed_into_the_conversation(entity, service, chat_model, logged_in_user):
    memory = await ChatMemoryService().create(entity, "We run tests on GCE", "note", logged_in_user)
    chat_model.turns = [text_turn("One test ", "failed on rc1")]

    started = await service.send(entity, "what failed?", logged_in_user)
    await chat_tasks.drain()

    path = await path_of(entity)
    assert [(node.role, node.content) for node in path] == [("user", "what failed?"),
                                                            ("assistant", "One test failed on rc1")]
    answer = path[-1]
    assert answer.node == started["assistant_node"]["node"]
    assert (answer.status, answer.prompt_tokens, answer.model_name) == ("done", 120, "test-model")
    assert str(memory["id"]) in answer.memory_snapshot
    request = chat_model.requests[0]
    assert "We run tests on GCE" in request.messages[0].content
    assert "1 failed" in request.messages[0].content
    assert request.messages[1].content == "Test User (@test_user): what failed?"
    assert request.tools
    assert (await ChatHistoryService(entity).state()).busy is None


async def test_a_tool_call_runs_and_the_model_answers_after_it(entity, service, chat_model, logged_in_user):
    chat_model.turns = [tool_turn(("write_memory", {"op": "add", "content": "Minor releases get sanity",
                                                    "kind": "note"})),
                        text_turn("Saved the convention")]

    await service.send(entity, "remember: minor releases get sanity", logged_in_user)
    await chat_tasks.drain()

    path = await path_of(entity)
    assert [node.role for node in path] == ["user", "assistant", "tool", "assistant"]
    assert path[1].tool_calls and path[2].tool_name == "write_memory" and path[2].status == "done"
    assert path[3].content == "Saved the convention"
    assert chat_model.requests[1].messages[-1].role == "tool"
    revision = (await ChatMemoryService().history(entity))[0]
    assert (revision["source"], revision["source_node"]) == ("chat", path[1].node)


async def test_the_tool_loop_stops_at_the_limit(entity, service, chat_model, logged_in_user):
    chat_model.turns = [tool_turn(("read_memory", {})) for _ in range(MAX_MODEL_CALLS + 2)]

    await service.send(entity, "loop forever", logged_in_user)
    await chat_tasks.drain()

    path = await path_of(entity)
    assert len(chat_model.requests) == MAX_MODEL_CALLS
    assert "limit" in path[-1].content.lower()
    assert path[-1].status == "done"


async def test_an_endpoint_error_fails_the_answer_and_frees_the_chat(entity, service, chat_model, logged_in_user):
    chat_model.turns = [[TextDelta("par"), ChatModelError("The model endpoint failed: boom")],
                        text_turn("fine now")]

    await service.send(entity, "first", logged_in_user)
    await chat_tasks.drain()
    failed = (await path_of(entity))[-1]
    await service.send(entity, "second", logged_in_user)
    await chat_tasks.drain()

    assert (failed.status, failed.content) == ("error", "par")
    assert "boom" in failed.error
    assert (await path_of(entity))[-1].content == "fine now"


async def test_a_second_question_waits_for_the_first(entity, service, chat_model, logged_in_user):
    gate = asyncio.Event()
    chat_model.turns = [[TextDelta("slow"), gate, Usage(1, 1), Finished("stop")]]

    await service.send(entity, "first", logged_in_user)
    with pytest.raises(ChatBusyError):
        await service.send(entity, "second", logged_in_user)
    gate.set()
    await chat_tasks.drain()


async def test_stop_ends_the_answer_as_stopped(entity, service, chat_model, logged_in_user):
    gate = asyncio.Event()
    chat_model.turns = [[TextDelta("partial "), gate, TextDelta("rest"), Usage(1, 1), Finished("stop")]]

    started = await service.send(entity, "first", logged_in_user)
    stopping = await service.stop(entity)
    gate.set()
    await chat_tasks.drain()

    answer = (await path_of(entity))[-1]
    assert stopping == started["assistant_node"]["node"]
    assert answer.status == "stopped"
    assert (await ChatHistoryService(entity).state()).busy is None


async def test_try_again_adds_a_sibling_answer(entity, service, chat_model, logged_in_user):
    chat_model.turns = [text_turn("first answer"), text_turn("second answer")]
    await service.send(entity, "what failed?", logged_in_user)
    await chat_tasks.drain()

    await service.regenerate(entity, logged_in_user)
    await chat_tasks.drain()

    _, nodes = await ChatHistoryService(entity).read()
    answers = [node for node in nodes if node.role == "assistant"]
    assert len({answer.parent for answer in answers}) == 1
    assert [node.content for node in await path_of(entity)] == ["what failed?", "second answer"]
    assert chat_model.requests[1].messages[-1].content.endswith("what failed?")


async def test_compaction_summarizes_and_the_next_prompt_starts_from_it(entity, service, chat_model,
                                                                       logged_in_user):
    chat_model.turns = [text_turn("an answer"), text_turn("They asked what failed"), text_turn("ok")]
    await service.send(entity, "what failed?", logged_in_user)
    await chat_tasks.drain()

    await service.compact(entity, logged_in_user)
    await chat_tasks.drain()
    await service.send(entity, "and now?", logged_in_user)
    await chat_tasks.drain()

    path = await path_of(entity)
    assert [node.role for node in path] == ["user", "assistant", "summary", "user", "assistant"]
    assert path[2].content == "They asked what failed"
    assert chat_model.requests[1].tools is None
    last = chat_model.requests[2].messages
    assert "They asked what failed" in last[0].content
    assert [message.role for message in last[1:]] == ["user"]


async def test_the_conversation_reports_context_and_model(entity, service, chat_model, logged_in_user):
    chat_model.turns = [text_turn("an answer")]
    await service.send(entity, "q", logged_in_user)
    await chat_tasks.drain()

    conversation = await service.conversation(entity)

    assert conversation["configured"] is True
    assert conversation["model"]["model"] == "test-model"
    assert conversation["context"]["window"] == 8000
    assert conversation["context"]["used"] >= 150
    assert [node["role"] for node in conversation["nodes"]] == ["user", "assistant"]


async def test_a_conversation_without_a_model(entity, service, clean_chat_config, logged_in_user):
    conversation = await service.conversation(entity)

    assert (conversation["configured"], conversation["model"]) == (False, None)
    with pytest.raises(ChatNotConfiguredError):
        await service.send(entity, "q", logged_in_user)


async def test_local_streams_get_tokens_and_another_worker_gets_the_flushed_node(entity, chat_model,
                                                                                 logged_in_user):
    asker_hub, other_hub = ChatHub(poll_seconds=0.05), ChatHub(poll_seconds=0.05)
    local_events, remote_events = [], []

    async def collect(hub: ChatHub, events: list):
        async for event in hub.subscribe(entity, logged_in_user):
            events.append(event)

    collectors = [asyncio.create_task(collect(asker_hub, local_events)),
                  asyncio.create_task(collect(other_hub, remote_events))]
    await asyncio.sleep(0.2)
    chat_model.turns = [text_turn("tok", "ens")]

    started = await ChatService(asker_hub).send(entity, "q", logged_in_user)
    await chat_tasks.drain()
    await asyncio.sleep(0.4)
    for collector in collectors:
        collector.cancel()

    answer_id = started["assistant_node"]["node"]
    assert [event["content"] for event in local_events if event["type"] == "delta"] == ["tok", "ens"]
    remote_answer = [event["node"] for event in remote_events
                     if event["type"] == "node" and event["node"]["node"] == answer_id]
    assert remote_answer and remote_answer[-1]["content"] == "tokens"
    assert any(event["type"] == "state" for event in remote_events)
    assert all(event["type"] != "delta" for event in remote_events)


async def test_presence_lists_users_with_the_chat_open(entity, logged_in_user):
    hub = ChatHub(poll_seconds=0.05, presence_seconds=0.05)
    events = []

    async def collect():
        async for event in hub.subscribe(entity, logged_in_user):
            events.append(event)

    collector = asyncio.create_task(collect())
    await asyncio.sleep(0.3)
    collector.cancel()

    presence = [event for event in events if event["type"] == "presence"]
    assert presence and presence[-1]["users"] == [logged_in_user.id]



async def test_another_worker_gets_a_snapshot_after_a_wipe(entity, chat_model, logged_in_user):
    asker_hub, other_hub = ChatHub(poll_seconds=0.05), ChatHub(poll_seconds=0.05)
    chat_model.turns = [text_turn("an answer")]
    await ChatService(asker_hub).send(entity, "q", logged_in_user)
    await chat_tasks.drain()
    events = []

    async def collect():
        async for event in other_hub.subscribe(entity, logged_in_user):
            events.append(event)

    collector = asyncio.create_task(collect())
    await asyncio.sleep(0.2)
    await ChatService(asker_hub).wipe(entity)
    await asyncio.sleep(0.4)
    collector.cancel()

    snapshots = [event for event in events if event["type"] == "snapshot"]
    assert snapshots and snapshots[-1]["conversation"]["nodes"] == []
