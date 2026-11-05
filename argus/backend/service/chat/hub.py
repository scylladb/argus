import asyncio
import contextvars
import logging
import signal
import threading
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from argus.backend.models.chat import ChatHistory, ChatPresence, ChatState
from argus.backend.models.web import User
from argus.backend.service.chat.config import ChatConfigService
from argus.backend.service.chat.conversation import conversation_json, node_json, state_event
from argus.backend.service.chat.entity import ChatEntity
from argus.backend.service.chat.history import as_utc, ensure_state
from argus.backend.service.chat.identity import ChatIdentityService, identity_json
from argus.backend.service.chat.memory import ChatMemoryService

LOGGER = logging.getLogger(__name__)
HEARTBEAT = {"type": "heartbeat"}
CLOSE = {"type": "close"}
PRESENCE_TTL_SECONDS = 30


def to_millis(moment: datetime | None) -> datetime | None:
    moment = as_utc(moment)
    return moment.replace(microsecond=moment.microsecond // 1000 * 1000) if moment else None


@dataclass(eq=False)
class Subscription:
    hub: "ChatHub"
    entity: ChatEntity
    user_id: UUID
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=2000))
    overflowed: bool = False
    closed: bool = False

    async def events(self) -> AsyncIterator[dict]:
        """Events until the stream's lifetime ends; the client then reconnects into a fresh snapshot."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.hub.stream_seconds
        while not (self.overflowed or self.closed) and (remaining := deadline - loop.time()) > 0:
            try:
                event = await asyncio.wait_for(self.queue.get(), min(self.hub.heartbeat_seconds, remaining))
                if event is CLOSE:
                    return
                yield event
            except TimeoutError:
                if deadline - loop.time() > 0:
                    yield HEARTBEAT

    def close(self) -> None:
        self.hub._unsubscribe(self)


class ChatHub:
    """Fans chat events out to this worker's open event streams. A watcher per
    entity with a local stream picks up what other workers wrote."""

    def __init__(self, poll_seconds: float = 0.5, presence_seconds: float = 10.0,
                 heartbeat_seconds: float = 10.0, release_memory_seconds: float = 2.0,
                 stream_seconds: float = 25.0) -> None:
        self.poll_seconds = poll_seconds
        self.stream_seconds = stream_seconds
        self.release_memory_seconds = release_memory_seconds
        self.presence_seconds = presence_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self._subscriptions: dict[UUID, set[Subscription]] = defaultdict(set)
        self._watchers: dict[UUID, asyncio.Task] = {}
        self._known: dict[UUID, dict[UUID, datetime | None]] = defaultdict(dict)

    def open(self, entity: ChatEntity, user: User) -> Subscription:
        subscription = Subscription(self, entity, user.id)
        self._subscriptions[entity.id].add(subscription)
        if entity.id not in self._watchers:
            self._watchers[entity.id] = asyncio.create_task(self._watch(entity), name=f"chat-watch-{entity.id}",
                                                            context=contextvars.Context())
        return subscription

    async def subscribe(self, entity: ChatEntity, user: User) -> AsyncIterator[dict]:
        subscription = self.open(entity, user)
        try:
            async for event in subscription.events():
                yield event
        finally:
            subscription.close()

    def _unsubscribe(self, subscription: Subscription) -> None:
        entity_id = subscription.entity.id
        subscribers = self._subscriptions.get(entity_id)
        if subscribers is None:
            return
        subscribers.discard(subscription)
        if not subscribers:
            self._subscriptions.pop(entity_id, None)
            self._known.pop(entity_id, None)
            if watcher := self._watchers.pop(entity_id, None):
                watcher.cancel()

    def close_all(self) -> None:
        """End every open stream now, so a server shutdown does not wait for them."""
        for subscriptions in list(self._subscriptions.values()):
            for subscription in list(subscriptions):
                subscription.closed = True
                try:
                    subscription.queue.put_nowait(CLOSE)
                except asyncio.QueueFull:
                    subscription.overflowed = True

    def publish(self, entity_id: UUID, event: dict) -> None:
        if event["type"] == "node":
            self._known[entity_id][event["node"]["node"]] = to_millis(event["node"]["updated_at"])
        for subscription in list(self._subscriptions.get(entity_id, ())):
            try:
                subscription.queue.put_nowait(event)
            except asyncio.QueueFull:
                subscription.overflowed = True

    async def _watch(self, entity: ChatEntity) -> None:
        state = await ensure_state(entity.id, entity.type)
        changed_at, memory_at = state.changed_at, state.memory_changed_at
        known = self._known[entity.id]
        for node in await ChatHistory.find(entity_id=entity.id).all():
            known.setdefault(node.node, to_millis(node.updated_at))
        other_ids = [release_id for release_id in entity.release_ids if release_id != entity.id]
        release_stamps = await self._memory_stamps(other_ids)
        presence: list[UUID] | None = None
        loop = asyncio.get_running_loop()
        presence_due = release_due = 0.0
        while True:
            try:
                memory_changed = False
                state = await ChatState.find_one(entity_id=entity.id)
                if state is not None:
                    if state.changed_at != changed_at:
                        changed_at = state.changed_at
                        await self._push_changes(entity, state)
                    if state.memory_changed_at != memory_at:
                        memory_at = state.memory_changed_at
                        memory_changed = True
                if other_ids and loop.time() >= release_due:
                    release_due = loop.time() + self.release_memory_seconds
                    stamps = await self._memory_stamps(other_ids)
                    memory_changed = memory_changed or stamps != release_stamps
                    release_stamps = stamps
                if memory_changed:
                    self.publish(entity.id, {"type": "memory", "memories": await ChatMemoryService().list(entity)})
                if loop.time() >= presence_due:
                    presence_due = loop.time() + self.presence_seconds
                    users = await self._refresh_presence(entity)
                    if users != presence:
                        presence = users
                        self.publish(entity.id, {"type": "presence", "users": users})
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a transient database error must not end the watcher
                LOGGER.warning("The chat watcher of %s failed a poll", entity.id, exc_info=True)
            await asyncio.sleep(self.poll_seconds)

    async def _push_changes(self, entity: ChatEntity, state: ChatState) -> None:
        nodes = list(await ChatHistory.find(entity_id=entity.id).all())
        known = self._known[entity.id]
        present = {node.node for node in nodes}
        if any(node_id not in present for node_id in known):
            known.clear()
            known.update({node.node: to_millis(node.updated_at) for node in nodes})
            conversation = conversation_json(entity, state, nodes, await ChatConfigService().resolve(),
                                             await ChatMemoryService().scopes(entity),
                                             identity_json(await ChatIdentityService().active()))
            self.publish(entity.id, {"type": "snapshot", "conversation": conversation})
            return
        for node in sorted(nodes, key=lambda node: node.node.time):
            stamp = to_millis(node.updated_at)
            if known.get(node.node) != stamp:
                self.publish(entity.id, {"type": "node", "node": node_json(node)})
        self.publish(entity.id, state_event(state, nodes, await ChatConfigService().resolve()))

    @staticmethod
    async def _memory_stamps(entity_ids: list[UUID]) -> dict[UUID, datetime | None]:
        stamps = {}
        for entity_id in entity_ids:
            state = await ChatState.find_one(entity_id=entity_id)
            stamps[entity_id] = state.memory_changed_at if state else None
        return stamps

    async def _refresh_presence(self, entity: ChatEntity) -> list[UUID]:
        now = datetime.now(UTC)
        for user_id in {subscription.user_id for subscription in self._subscriptions.get(entity.id, ())}:
            await ChatPresence(entity_id=entity.id, user_id=user_id, seen_at=now).save(ttl=PRESENCE_TTL_SECONDS)
        return sorted((row.user_id for row in await ChatPresence.find(entity_id=entity.id).all()), key=str)


default_hub = ChatHub()


def close_streams_on_exit(loop: asyncio.AbstractEventLoop, hub: ChatHub = default_hub) -> None:
    """Chain the server's SIGTERM and SIGINT handlers so open event streams end
    first; a graceful shutdown waits for every open response."""
    if threading.current_thread() is not threading.main_thread():
        return
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous = signal.getsignal(signum)
        if not callable(previous):
            continue

        def handler(received, frame, previous=previous):
            loop.call_soon_threadsafe(hub.close_all)
            previous(received, frame)

        signal.signal(signum, handler)
