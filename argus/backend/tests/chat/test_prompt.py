import json
import uuid
from datetime import UTC, datetime, timedelta
from uuid import uuid1, uuid4

from argus.backend.models.chat import ChatHistory
from argus.backend.models.web import User
from argus.backend.service.chat.entity import ChatEntity
from argus.backend.service.chat.prompt import (
    TOOL_RESULT_LIMIT,
    build_system_prompt,
    compact_summary,
    context_stats,
    memory_lines,
    prompt_memories,
    to_messages,
)

ENTITY_ID = uuid.uuid4()
ALICE = User(id=uuid.uuid4(), username="alice", full_name="Alice Smith", email="a@x", password="",
             registration_date=datetime.now(UTC), roles=[])


def node(role: str, content: str = "", parent: ChatHistory | None = None, **fields) -> ChatHistory:
    return ChatHistory(entity_id=ENTITY_ID, entity_type="release", node=uuid1(), role=role, content=content,
                       parent=parent.node if parent else None, **fields)


SUMMARY = {
    "release_name": "scylla-2034.1",
    "families": [{
        "family": "2034.1.0",
        "rollup": {"version": None,
                   "counts": {"executed": 3, "passed": 1, "failed": 1, "aborted": 1, "in_progress": 0,
                              "pending": 2, "issues_new": 1, "issues_existing": 0, "issues_fixed": 0},
                   "tests": [], "issues": [{"key": "SCYLLA-1", "status": "open", "title": "crash"}]},
        "versions": [{"version": "2034.1.0~rc1",
                      "counts": {"executed": 3, "passed": 1, "failed": 1, "aborted": 1, "in_progress": 0,
                                 "pending": 2, "issues_new": 1, "issues_existing": 0, "issues_fixed": 0},
                      "tests": [{"test_name": "upgrade_test", "group_name": "upgrades", "status": "failed"},
                                {"test_name": "longevity", "group_name": "long", "status": "aborted"},
                                {"test_name": "sanity", "group_name": "basic", "status": "passed"}],
                      "issues": []}],
    }],
}


def test_the_system_prompt_names_the_entity_memories_and_summary():
    entity = ChatEntity(ENTITY_ID, "view", "Week1 plan", (uuid.uuid4(),), frozenset())
    memories = [{"id": uuid1(), "kind": "note", "content": "We run tests on GCE", "entity_type": "release",
                 "entity_name": "scylla-2034.1", "updated_by": ALICE.id}]

    prompt = build_system_prompt(entity, memories, "SUMMARY TEXT", {ALICE.id: ALICE},
                                 datetime(2034, 1, 2, tzinfo=UTC), tools=True)

    assert "view Week1 plan" in prompt
    assert "We run tests on GCE" in prompt and "release scylla-2034.1" in prompt and "@alice" in prompt
    assert "SUMMARY TEXT" in prompt
    assert "2034-01-02" in prompt


def test_the_compact_summary_has_counts_failed_tests_and_open_issues():
    text = compact_summary([SUMMARY])

    assert "scylla-2034.1" in text
    assert "2034.1.0~rc1: 3 executed: 1 passed, 1 failed, 1 aborted" in text
    assert "2 planned but not started" in text
    assert "upgrades/upgrade_test (failed)" in text and "long/longevity (aborted)" in text
    assert "basic/sanity" not in text
    assert "SCYLLA-1" in text


def test_messages_carry_the_asker_and_skip_what_a_summary_replaced():
    first = node("user", "old question", user_id=ALICE.id)
    old_answer = node("assistant", "old answer", first)
    summary = node("summary", "They asked about rc1", old_answer)
    question = node("user", "what failed?", summary, user_id=ALICE.id)
    call = node("assistant", "", question, tool_calls=json.dumps([{"id": "c1", "name": "get_summary",
                                                                     "arguments": "{}"}]))
    result = node("tool", "x" * (TOOL_RESULT_LIMIT + 500), call, tool_call_id="c1", tool_name="get_summary")
    answer = node("assistant", "Two tests", result, reasoning="thinking")

    messages = to_messages([first, old_answer, summary, question, call, result, answer], {ALICE.id: ALICE})

    assert [message.role for message in messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert "They asked about rc1" in messages[0].content
    assert messages[1].content == "Alice Smith (@alice): what failed?"
    assert messages[2].tool_calls[0].name == "get_summary"
    assert len(messages[3].content) <= TOOL_RESULT_LIMIT + 40
    assert messages[4].content == "Two tests"


def test_a_tool_call_without_a_result_is_dropped():
    question = node("user", "q", user_id=ALICE.id)
    call = node("assistant", "partial", question, status="stopped",
                tool_calls=json.dumps([{"id": "c1", "name": "get_summary", "arguments": "{}"}]))

    messages = to_messages([question, call], {ALICE.id: ALICE})

    assert messages[-1].role == "assistant" and messages[-1].tool_calls == []


def test_an_action_outcome_reaches_the_model_as_a_note_on_the_next_question():
    question = node("user", "rerun them", user_id=ALICE.id)
    answer = node("assistant", "Confirm the card", question)
    card = node("action", "", answer, action_state="done", action=json.dumps({
        "kind": "execute_tests", "confirmed_by": str(ALICE.id),
        "proposal": {"tests": [{"test": "upgrades/upgrade_test"}]},
        "results": [{"test": "upgrades/upgrade_test", "queue_item": 7, "build_number": 42, "error": None}]}))
    pending = node("action", "", card, action_state="pending", action=json.dumps({"kind": "link_issue"}))
    follow_up = node("user", "did they start?", pending, user_id=ALICE.id)

    messages = to_messages([question, answer, card, pending, follow_up], {ALICE.id: ALICE})

    assert [message.role for message in messages] == ["user", "assistant", "user"]
    note, asked = messages[-1].content.split("\n\n")
    assert note.startswith("[Argus] Alice Smith (@alice) confirmed execute_tests")
    assert "upgrades/upgrade_test started as build 42" in note
    assert asked == "Alice Smith (@alice): did they start?"


def test_context_stats_start_from_the_last_usage():
    question = node("user", "q" * 400, user_id=ALICE.id)
    answer = node("assistant", "a" * 40, question, prompt_tokens=1000, completion_tokens=200)
    follow_up = node("user", "b" * 400, answer, user_id=ALICE.id)

    stats = context_stats([question, answer, follow_up], 8000)

    assert stats == {"window": 8000, "used": 1300, "last_prompt_tokens": 1000, "estimated_tokens": 100,
                     "messages_since_compaction": 3, "warn_at": 6000, "compact_at": 7200}


def test_memories_fit_a_budget_with_the_chats_own_first():
    own, other = uuid4(), uuid4()
    now = datetime.now(UTC)

    def memory(owner, content: str, minutes_ago: int) -> dict:
        return {"id": str(uuid4()), "entity_id": owner, "content": content, "kind": "note", "entity_type": "view",
                "entity_name": "v", "updated_by": None, "updated_at": now - timedelta(minutes=minutes_ago)}

    memories = [memory(other, "release, new", 1), memory(own, "view, old", 60), memory(other, "x" * 9000, 0)]

    shown, left_out = prompt_memories(memories, own)

    assert [entry["content"] for entry in shown] == ["view, old", "release, new"]
    assert left_out == 1
    assert "1 more memories do not fit here" in memory_lines(shown, {}, left_out)
