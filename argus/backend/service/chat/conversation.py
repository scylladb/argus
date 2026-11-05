import json

from argus.backend.models.chat import ChatHistory, ChatState
from argus.backend.service.chat.config import DEFAULT_CONTEXT_WINDOW, ResolvedModel
from argus.backend.service.chat.entity import ChatEntity
from argus.backend.service.chat.history import active_path, as_utc
from argus.backend.service.chat.prompt import context_stats


def node_json(node: ChatHistory) -> dict:
    action = json.loads(node.action) if node.action else None
    if action is not None:
        action["state"] = node.action_state
    return {
        "node": node.node,
        "parent": node.parent,
        "role": node.role,
        "content": node.content,
        "reasoning": node.reasoning,
        "user_id": node.user_id,
        "tool_calls": json.loads(node.tool_calls) if node.tool_calls else [],
        "tool_call_id": node.tool_call_id,
        "tool_name": node.tool_name,
        "action": action,
        "model_name": node.model_name,
        "usage": ({"prompt_tokens": node.prompt_tokens, "completion_tokens": node.completion_tokens or 0}
                  if node.prompt_tokens is not None else None),
        "memory_snapshot": json.loads(node.memory_snapshot) if node.memory_snapshot else [],
        "status": node.status,
        "error": node.error,
        "hidden": node.hidden,
        "created_at": as_utc(node.created_at),
        "updated_at": as_utc(node.updated_at),
    }


def model_json(model: ResolvedModel | None) -> dict | None:
    if model is None:
        return None
    return {"connection": model.connection, "model": model.model, "context_window": model.context_window,
            "tools": model.tools}


def busy_json(state: ChatState) -> dict | None:
    if not state.busy:
        return None
    return {"node": state.busy, "user_id": state.busy_user, "since": as_utc(state.busy_since)}


def state_event(state: ChatState, nodes: list[ChatHistory], model: ResolvedModel | None) -> dict:
    window = model.context_window if model else DEFAULT_CONTEXT_WINDOW
    return {"type": "state", "head": state.head, "busy": busy_json(state),
            "context": context_stats(active_path(nodes, state.head), window)}


def conversation_json(entity: ChatEntity, state: ChatState, nodes: list[ChatHistory],
                      model: ResolvedModel | None, scopes: list[dict], assistant: dict | None) -> dict:
    window = model.context_window if model else DEFAULT_CONTEXT_WINDOW
    return {
        "entity_id": entity.id,
        "entity_type": entity.type,
        "entity_name": entity.name,
        "scopes": scopes,
        "configured": model is not None,
        "model": model_json(model),
        "assistant": assistant,
        "head": state.head,
        "busy": busy_json(state),
        "nodes": [node_json(node) for node in sorted(nodes, key=lambda node: node.node.time)],
        "context": context_stats(active_path(nodes, state.head), window),
    }
