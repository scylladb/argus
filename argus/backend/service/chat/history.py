from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from coodie.exceptions import DocumentNotFound

from argus.backend.error_handlers import APIException
from argus.backend.models.chat import ChatHistory, ChatState
from argus.backend.models.web import User
from argus.backend.service.chat.entity import ChatEntity

STALE_LOCK = timedelta(minutes=5)
TURN_ROOTS = ("user", "summary")


class ChatHistoryError(APIException):
    pass


class ChatBusyError(APIException):
    pass


def as_utc(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def children_of(nodes: Iterable[ChatHistory]) -> dict[UUID | None, list[ChatHistory]]:
    children: dict[UUID | None, list[ChatHistory]] = defaultdict(list)
    for node in nodes:
        children[node.parent].append(node)
    return children


def active_path(nodes: list[ChatHistory], head: UUID | None) -> list[ChatHistory]:
    by_id = {node.node: node for node in nodes}
    path = []
    current = by_id.get(head) if head else None
    while current is not None:
        path.append(current)
        current = by_id.get(current.parent) if current.parent else None
    return list(reversed(path))


def newest_leaf(nodes: list[ChatHistory], start: ChatHistory) -> ChatHistory:
    children = children_of(node for node in nodes if not node.hidden)
    current = start
    while visible := children.get(current.node):
        current = max(visible, key=lambda node: node.node.time)
    return current


def describe_user(user: User | None) -> str:
    if user is None:
        return "another user"
    return f"{user.full_name or user.username} (@{user.username})"


async def ensure_state(entity_id: UUID, entity_type: str) -> ChatState:
    state = await ChatState.find_one(entity_id=entity_id)
    if state is None:
        await ChatState(entity_id=entity_id, entity_type=entity_type).insert()
        state = await ChatState.get(entity_id=entity_id)
    return state


async def touch_state(entity_id: UUID, entity_type: str, memory: bool = False) -> None:
    await ensure_state(entity_id, entity_type)
    field = "memory_changed_at" if memory else "changed_at"
    await ChatState(entity_id=entity_id).update(**{field: datetime.now(UTC)})


class ChatHistoryService:
    def __init__(self, entity: ChatEntity) -> None:
        self.entity = entity

    async def state(self) -> ChatState:
        return await ensure_state(self.entity.id, self.entity.type)

    async def nodes(self) -> list[ChatHistory]:
        return list(await ChatHistory.find(entity_id=self.entity.id).all())

    async def read(self) -> tuple[ChatState, list[ChatHistory]]:
        return await self.state(), await self.nodes()

    async def touch(self, memory: bool = False) -> None:
        await touch_state(self.entity.id, self.entity.type, memory)

    async def append(self, **fields) -> ChatHistory:
        node = ChatHistory(entity_id=self.entity.id, entity_type=self.entity.type, **fields)
        await node.save()
        await self.touch()
        return node

    async def flush(self, node: ChatHistory, **fields) -> None:
        await node.update(updated_at=datetime.now(UTC), **fields)
        await self.touch()

    async def move_head(self, expected: UUID | None, new: UUID | None) -> bool:
        await self.state()
        result = await ChatState(entity_id=self.entity.id).update(if_conditions={"head": expected}, head=new)
        if result.applied:
            await self.touch()
        return result.applied

    async def acquire(self, user: User, node: UUID, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        state = await self.state()
        lock = {"busy": node, "busy_user": user.id, "busy_since": now, "stop_requested": None}
        result = await ChatState(entity_id=self.entity.id).update(if_conditions={"busy": None}, **lock)
        if result.applied:
            await self.touch()
            return
        state = await self.state()
        if state.busy and as_utc(state.busy_since) < now - STALE_LOCK:
            taken = await ChatState(entity_id=self.entity.id).update(if_conditions={"busy": state.busy}, **lock)
            if taken.applied:
                await self._abandon(state.busy)
                await self.touch()
                return
            state = await self.state()
        raise ChatBusyError(f"Answering the question of {describe_user(await self._user(state.busy_user))}")

    async def release(self, node: UUID) -> None:
        result = await ChatState(entity_id=self.entity.id).update(if_conditions={"busy": node}, busy=None,
                                                                  busy_user=None, busy_since=None,
                                                                  stop_requested=None)
        if result.applied:
            await self.touch()

    async def ensure_idle(self) -> ChatState:
        state = await self.state()
        if state.busy:
            raise ChatBusyError(f"Answering the question of {describe_user(await self._user(state.busy_user))}")
        return state

    async def undo(self) -> UUID | None:
        state = await self.ensure_idle()
        nodes = await self.nodes()
        path = active_path(nodes, state.head)
        root = next((node for node in reversed(path) if node.role in TURN_ROOTS), None)
        if root is None:
            raise ChatHistoryError("There is nothing to undo")
        await self._hide_subtree(nodes, root)
        if not await self.move_head(state.head, root.parent):
            raise ChatHistoryError("The conversation changed meanwhile; try again")
        return root.parent

    async def set_head(self, node: UUID) -> UUID:
        state = await self.ensure_idle()
        nodes = await self.nodes()
        target = next((candidate for candidate in nodes if candidate.node == node and not candidate.hidden), None)
        if target is None:
            raise ChatHistoryError(f"No message {node} in this conversation")
        leaf = newest_leaf(nodes, target)
        if not await self.move_head(state.head, leaf.node):
            raise ChatHistoryError("The conversation changed meanwhile; try again")
        return leaf.node

    async def wipe(self) -> None:
        await self.ensure_idle()
        await ChatHistory.find(entity_id=self.entity.id).delete()
        await ChatState(entity_id=self.entity.id).update(head=None, stop_requested=None)
        await self.touch()

    async def _hide_subtree(self, nodes: list[ChatHistory], root: ChatHistory) -> None:
        children = children_of(nodes)
        pending = [root]
        now = datetime.now(UTC)
        while pending:
            current = pending.pop()
            await current.update(hidden=True, updated_at=now)
            pending.extend(children.get(current.node, []))

    async def _abandon(self, node: UUID) -> None:
        abandoned = await ChatHistory.find_one(entity_id=self.entity.id, node=node)
        if abandoned is not None and abandoned.status == "streaming":
            await abandoned.update(status="error", error="The answer was interrupted", updated_at=datetime.now(UTC))

    @staticmethod
    async def _user(user_id: UUID | None) -> User | None:
        if user_id is None:
            return None
        try:
            return await User.get(id=user_id)
        except DocumentNotFound:
            return None
