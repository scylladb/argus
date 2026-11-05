import time

import pytest
from starlette.testclient import TestClient

from argus.backend.service.chat.llm import ChatModelError, Finished, TextDelta, Usage
from argus.backend.service.chat.prompt import COMPACT_INSTRUCTION
from argus.backend.tests.chat.helpers import seed_entity_release, text_turn

pytestmark = pytest.mark.docker_required

FULL = [TextDelta("a long answer"), Usage(7600, 100), Finished("stop")]


def ok(response):
    body = response.json()
    assert body["status"] == "ok", body
    return body["response"]


def ask(client: TestClient, base: str, content: str) -> dict:
    ok(client.post(f"{base}/messages", json={"content": content}))
    deadline = time.monotonic() + 10
    while (conversation := ok(client.get(base)))["busy"] is not None and time.monotonic() < deadline:
        time.sleep(0.05)
    return conversation


@pytest.fixture
async def base(release_manager_service) -> str:
    seeded = await seed_entity_release(release_manager_service)
    return f"/api/v1/chat/release/{seeded.release.id}"


def path_of(conversation: dict) -> list[dict]:
    nodes = {node["node"]: node for node in conversation["nodes"]}
    path, current = [], nodes.get(conversation["head"])
    while current:
        path.append(current)
        current = nodes.get(current["parent"])
    return list(reversed(path))


async def test_a_full_context_is_compacted_before_the_next_answer(chat_client: TestClient, chat_model, base):
    chat_model.turns = [text_turn("short"), FULL, text_turn("SUMMARY OF IT"), text_turn("the answer")]
    ask(chat_client, base, "q1")
    before = ask(chat_client, base, "q2")

    after = ask(chat_client, base, "q3")

    assert before["context"]["used"] >= before["context"]["compact_at"] == 7200
    assert before["context"]["warn_at"] == 6000
    roles = [(node["role"], node["content"]) for node in path_of(after)]
    assert roles[-3:] == [("summary", "SUMMARY OF IT"), ("user", "q3"), ("assistant", "the answer")]
    summary = path_of(after)[-3]
    assert summary["auto"] is True and summary["status"] == "done"
    assert chat_model.requests[2].messages[0].content.startswith(COMPACT_INSTRUCTION)
    assert "Summary of the earlier conversation:\nSUMMARY OF IT" in chat_model.requests[3].messages[0].content
    assert after["context"]["messages_since_compaction"] == 2


async def test_a_failed_compaction_still_answers(chat_client: TestClient, chat_model, base):
    chat_model.turns = [FULL, [ChatModelError("the model is down")], text_turn("the answer")]
    ask(chat_client, base, "q1")

    after = ask(chat_client, base, "q2")

    summary, question, answer = path_of(after)[-3:]
    assert (summary["role"], summary["status"]) == ("summary", "error")
    assert (question["content"], answer["content"], answer["status"]) == ("q2", "the answer", "done")
    assert "Summary of the earlier conversation" not in chat_model.requests[2].messages[0].content
