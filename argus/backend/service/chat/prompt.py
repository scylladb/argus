import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from uuid import UUID

from argus.backend.models.chat import ChatHistory
from argus.backend.models.web import User
from argus.backend.service.chat.entity import ChatEntity
from argus.backend.service.chat.llm import ChatMessage, ToolCall

TEMPLATE = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")
TOOL_RESULT_LIMIT = 6000
FAILED_TEST_LIMIT = 40
OPEN_ISSUE_LIMIT = 30
FAILED_STATUSES = ("failed", "test_error", "error", "aborted")
TOOL_RULES = """- Use the tools to look things up before you answer. Prefer one precise call
  over many broad ones.
- To explain why a run failed, read its events (read_run shows the first
  errors; get_run_events lists them) before you answer. Filter runs by version
  when the question names one.
- Starting tests, and linking or unlinking issues, only proposes the change.
  Argus shows the proposal to the users as a card, and nothing happens until
  one of them confirms it. Tell the user to confirm the card.
- Use write_memory when a user asks you to remember a convention, or to add
  a finding to the release summary (kind "finding")."""
NO_TOOL_RULES = "- You have no tools in this chat. Answer from the summary and the memories."
COMPACT_INSTRUCTION = """Summarize the conversation below for later reference. Keep the facts,
the decisions, the open requests, the test names, the versions, and who asked
for what. Write at most 250 words, as a short list."""


def user_label(user_id: UUID | None, users: Mapping[UUID, User]) -> str:
    user = users.get(user_id) if user_id else None
    if user is None:
        return "Unknown user"
    return f"{user.full_name or user.username} (@{user.username})"


def truncate(text: str, limit: int = TOOL_RESULT_LIMIT) -> str:
    return text if len(text) <= limit else f"{text[:limit]}\n…[truncated]"


def counts_text(counts: Mapping[str, int]) -> str:
    return (f"{counts['executed']} executed: {counts['passed']} passed, {counts['failed']} failed, "
            f"{counts['aborted']} aborted; {counts['in_progress']} in progress; "
            f"{counts['pending']} planned but not started; issues: {counts['issues_new']} new, "
            f"{counts['issues_existing']} existing, {counts['issues_fixed']} fixed")


def compact_summary(summaries: list[dict]) -> str:
    if not summaries:
        return "No summary is available."
    lines = []
    failed_left, issues_left = FAILED_TEST_LIMIT, OPEN_ISSUE_LIMIT
    for release in summaries:
        lines.append(f"### Release {release['release_name']}")
        if not release["families"]:
            lines.append("No tested versions yet.")
        for family in release["families"]:
            rollup = family["rollup"]
            lines.append(f"- Family {family['family']}: {counts_text(rollup['counts'])}")
            for version in reversed(family["versions"]):
                lines.append(f"  - {version['version']}: {counts_text(version['counts'])}")
                failing = [test for test in version["tests"] if test["status"] in FAILED_STATUSES]
                if failing and failed_left > 0:
                    shown = failing[:failed_left]
                    failed_left -= len(shown)
                    names = ", ".join(f"{test['group_name']}/{test['test_name']} ({test['status']})" for test in shown)
                    lines.append(f"    - not passing: {names}")
            open_issues = [issue for issue in rollup["issues"] if issue["status"] == "open"][:max(issues_left, 0)]
            issues_left -= len(open_issues)
            if open_issues:
                lines.append("  - open issues: " + "; ".join(
                    f"{issue['key']} {issue.get('title') or ''}".strip() for issue in open_issues))
    return "\n".join(lines)


def memory_lines(memories: list[dict], users: Mapping[UUID, User]) -> str:
    if not memories:
        return "No memories yet."
    return "\n".join(
        f"- [{memory['id']}] {memory['kind']} of {memory['entity_type']} {memory['entity_name']}, "
        f"by {user_label(memory['updated_by'], users)}: {memory['content']}"
        for memory in memories
    )


def scope_text(entity: ChatEntity) -> str:
    if entity.type == "release":
        return f"This chat covers every test of the release {entity.name}."
    return (f"This chat covers the tests of the view {entity.name}, which come from "
            f"{len(entity.release_ids)} release(s). Tools only reach these tests.")


def build_system_prompt(entity: ChatEntity, memories: list[dict], summary_text: str, users: Mapping[UUID, User],
                        now: datetime, tools: bool, assistant_name: str | None = None) -> str:
    return TEMPLATE.format_map({
        "identity": f"{assistant_name}, the assistant of Argus" if assistant_name else "the assistant of Argus",
        "entity_kind": entity.type,
        "entity_name": entity.name,
        "date": now.strftime("%Y-%m-%d"),
        "tool_rules": TOOL_RULES if tools else NO_TOOL_RULES,
        "scope": scope_text(entity),
        "memories": memory_lines(memories, users),
        "summary": summary_text,
    })


def _tool_calls(node: ChatHistory) -> list[ToolCall]:
    return [ToolCall(**call) for call in json.loads(node.tool_calls)] if node.tool_calls else []


ZEUS_NOTE_LIMIT = 1500


def _result_text(kind: str, result: dict) -> str:
    if kind == "zeus_investigation":
        text = f"{result['test']} (run {result['run_id']}): {result['status']}"
        if result.get("error"):
            return f"{text}, {result['error']}"
        if result.get("response"):
            return f"{text}. Report: {truncate(result['response'], ZEUS_NOTE_LIMIT)}"
        return text
    if result.get("error"):
        return f"{result.get('test', kind)} failed: {result['error']}"
    match kind:
        case "execute_tests":
            started = f"build {result['build_number']}" if result.get("build_number") else \
                f"queue item {result['queue_item']}"
            return f"{result['test']} started as {started}"
        case "link_issue":
            return "the issue is linked"
        case _:
            return f"{result.get('issue')} is unlinked"


def action_note(node: ChatHistory, users: Mapping[UUID, User]) -> str | None:
    action = json.loads(node.action) if node.action else {}
    kind = action.get("kind", "action")
    if kind in ("show_run", "zeus_report"):
        return None
    if node.action_state == "done":
        who = user_label(UUID(action["confirmed_by"]), users) if action.get("confirmed_by") else "A user"
        results = "; ".join(_result_text(kind, result) for result in action.get("results", []))
        if kind == "zeus_investigation":
            return f"{who} queued Zeus investigations: {results}"
        return f"{who} confirmed {kind}: {results}"
    if node.action_state == "dismissed":
        who = user_label(UUID(action["dismissed_by"]), users) if action.get("dismissed_by") else "A user"
        return f"{who} dismissed the {kind} proposal"
    return None


def node_user_ids(path: list[ChatHistory]) -> set[UUID]:
    ids = {node.user_id for node in path if node.user_id}
    for node in path:
        if node.role == "action" and node.action:
            action = json.loads(node.action)
            ids.update(UUID(action[key]) for key in ("confirmed_by", "dismissed_by") if action.get(key))
    return ids


def to_messages(path: list[ChatHistory], users: Mapping[UUID, User]) -> list[ChatMessage]:
    """The model's view of the active path. A leading system message carries the
    newest compaction summary; the caller merges it into its system prompt."""
    start = max((index for index, node in enumerate(path) if node.role == "summary"), default=-1)
    messages: list[ChatMessage] = []
    if start >= 0:
        messages.append(ChatMessage("system", f"Summary of the earlier conversation:\n{path[start].content}"))
    nodes = path[start + 1:]
    answered = {node.tool_call_id for node in nodes if node.role == "tool" and node.tool_call_id}
    notes: list[str] = []
    for node in nodes:
        match node.role:
            case "user":
                content = f"{user_label(node.user_id, users)}: {node.content}"
                if notes:
                    content = "\n".join(f"[Argus] {note}" for note in notes) + "\n\n" + content
                    notes = []
                messages.append(ChatMessage("user", content))
            case "assistant":
                calls = [call for call in _tool_calls(node) if call.id in answered]
                if node.content or calls:
                    messages.append(ChatMessage("assistant", node.content, tool_calls=calls))
            case "tool" if node.tool_call_id:
                messages.append(ChatMessage("tool", truncate(node.content), tool_call_id=node.tool_call_id))
            case "action":
                if note := action_note(node, users):
                    notes.append(note)
    if notes:
        messages.append(ChatMessage("user", "\n".join(f"[Argus] {note}" for note in notes)))
    return messages


def estimate_tokens(text: str | None) -> int:
    return len(text or "") // 4


def context_stats(path: list[ChatHistory], window: int) -> dict:
    last = max((index for index, node in enumerate(path) if node.prompt_tokens is not None), default=-1)
    base = 0
    last_prompt = None
    if last >= 0:
        last_prompt = path[last].prompt_tokens
        base = last_prompt + (path[last].completion_tokens or 0)
    estimated = sum(estimate_tokens(node.content) for node in path[last + 1:])
    compacted = max((index for index, node in enumerate(path) if node.role == "summary"), default=-1)
    since = sum(1 for node in path[compacted + 1:] if node.role in ("user", "assistant"))
    return {"window": window, "used": base + estimated, "last_prompt_tokens": last_prompt,
            "estimated_tokens": estimated, "messages_since_compaction": since}
