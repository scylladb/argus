"""Embeds SCT ERROR and CRITICAL events, marks duplicates within a run and starts their summaries.

The submit route runs ``process()`` as a background task once it has answered. The
``sct_unprocessed_events`` row of an event stays until the event is handled, so ``sweep()``
picks up whatever a background task did not finish.

Deduplication is scoped to a single run: an event's embedding is compared only against the
embeddings already stored for the same ``run_id``. Because ``run_id`` is the partition key of
both embedding tables, this is a single-partition read.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from itertools import groupby
from uuid import UUID
from weakref import WeakValueDictionary

from argus.backend.models.argus_ai import SCTCriticalEventEmbedding, SCTErrorEventEmbedding
from argus.backend.plugins.sct.events.embedding import EventEmbedder, cosine
from argus.backend.plugins.sct.events.summary_dispatcher import SummaryDispatcher, UniqueEvent
from argus.backend.plugins.sct.testrun import SCTEvent, SCTEventSeverity, SCTUnprocessedEvent
from argus.backend.util.config import Config

LOGGER = logging.getLogger(__name__)

# Maximum cosine distance for two embeddings to be considered duplicates.
DUPLICATE_DISTANCE_THRESHOLD = 0.05

EMBEDDING_MODELS = {
    SCTEventSeverity.ERROR.value: SCTErrorEventEmbedding,
    SCTEventSeverity.CRITICAL.value: SCTCriticalEventEmbedding,
}


@dataclass(frozen=True, slots=True)
class QueuedEvent:
    run_id: UUID
    severity: str
    ts: datetime


def _utc_ms(ts: datetime) -> datetime:
    """The database keeps milliseconds and returns naive UTC; compare timestamps in that precision."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.replace(microsecond=ts.microsecond // 1000 * 1000)


class EventProcessor:
    def __init__(self, embedder: EventEmbedder, dispatcher: SummaryDispatcher):
        self._embedder = embedder
        self._dispatcher = dispatcher
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="event-embedder")
        self._locks: WeakValueDictionary[UUID, asyncio.Lock] = WeakValueDictionary()

    async def process(self, events: list[QueuedEvent]) -> None:
        unique: list[UniqueEvent] = []
        for run_id, run_events in groupby(events, key=lambda event: event.run_id):
            lock = self._locks.setdefault(run_id, asyncio.Lock())
            async with lock:
                for event in run_events:
                    try:
                        if result := await self._process_one(event):
                            unique.append(result)
                    except Exception:  # noqa: BLE001 - the queue row stays for the sweep
                        LOGGER.exception(
                            "Could not process event run_id=%s severity=%s ts=%s",
                            event.run_id,
                            event.severity,
                            event.ts,
                        )
        await self._dispatcher.summarize(unique)

    async def sweep(self, min_age: timedelta) -> int:
        cutoff = datetime.now(tz=UTC) - min_age
        stale = [
            QueuedEvent(run_id=row.run_id, severity=row.severity, ts=row.ts)
            for row in await SCTUnprocessedEvent.find().all()
            if row.queued_at is None or _utc_ms(row.queued_at) <= cutoff
        ]
        stale.sort(key=lambda event: (event.run_id, event.ts))
        await self.process(stale)
        return len(stale)

    async def _process_one(self, event: QueuedEvent) -> UniqueEvent | None:
        stored = await SCTEvent.find(run_id=event.run_id, severity=event.severity, ts=event.ts).only("message").first()
        if not stored or not stored.message:
            LOGGER.warning("Event run_id=%s severity=%s ts=%s has no message", event.run_id, event.severity, event.ts)
            await self._dequeue(event)
            return None

        try:
            vector = await asyncio.get_running_loop().run_in_executor(
                self._executor, self._embedder.embed, stored.message
            )
        except ValueError as exc:
            LOGGER.warning("Event run_id=%s ts=%s cannot be embedded: %s", event.run_id, event.ts, exc)
            await self._dequeue(event)
            return None

        model = EMBEDDING_MODELS[event.severity]
        own_ts = _utc_ms(event.ts)
        match = next(
            (
                row
                for row in await model.find(run_id=event.run_id).only("ts", "embedding").all()
                if _utc_ms(row.ts) != own_ts and cosine(row.embedding, vector) < DUPLICATE_DISTANCE_THRESHOLD
            ),
            None,
        )
        if match:
            original = (
                await SCTEvent.find(run_id=event.run_id, severity=event.severity, ts=match.ts).only("event_id").first()
            )
            if original:
                await SCTEvent.find(run_id=event.run_id, severity=event.severity, ts=event.ts).update(
                    duplicate_id=original.event_id
                )
                await self._dequeue(event)
                return None

        await model(run_id=event.run_id, ts=event.ts, embedding=vector.tolist()).save()
        await self._dequeue(event)
        return UniqueEvent(run_id=event.run_id, severity=event.severity, ts=event.ts, message=stored.message)

    @staticmethod
    async def _dequeue(event: QueuedEvent) -> None:
        await SCTUnprocessedEvent.find(run_id=event.run_id, severity=event.severity, ts=event.ts).delete()


@cache
def get_event_processor() -> EventProcessor:
    return EventProcessor(EventEmbedder(), SummaryDispatcher(Config.load_yaml_config()))
