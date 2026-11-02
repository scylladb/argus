from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from argus.backend.plugins.sct.events.embedding import EventEmbedder
from argus.backend.plugins.sct.events.processor import EventProcessor, QueuedEvent
from argus.backend.plugins.sct.events.summary_dispatcher import SummaryDispatcher
from argus.backend.plugins.sct.service import SCTService
from argus.backend.plugins.sct.testrun import SCTEventSeverity, SCTUnprocessedEvent
from argus.backend.service.client_service import ClientService
from argus.backend.tests.sct_events.helpers import (
    event_payload,
    queued,
    stored_embedding,
    stored_events,
    submitted_run,
)

STALL = "Reactor stalled for 512 ms on shard 3, backtrace: 0x1234 0x5678"


@pytest.fixture
def processor() -> EventProcessor:
    return EventProcessor(EventEmbedder(), SummaryDispatcher({}))


@pytest.fixture
async def run_id(client_service: ClientService, fake_test) -> UUID:
    return await submitted_run(client_service, fake_test)


async def _submit(sct_service: SCTService, run_id: UUID, severity: str, message: str,
                  ts: float | None = None) -> QueuedEvent:
    payload = event_payload(run_id, severity, message, ts)
    await sct_service.submit_event(run_id, payload)
    return QueuedEvent(run_id=run_id, severity=severity, ts=datetime.fromtimestamp(payload["ts"], tz=UTC))


async def test_error_and_critical_events_get_embeddings_in_their_tables(processor, sct_service, run_id):
    error = await _submit(sct_service, run_id, "ERROR", STALL)
    critical = await _submit(sct_service, run_id, "CRITICAL", "Scylla process aborted on node-2")

    await processor.process([error, critical])

    assert len(await stored_embedding(run_id, "ERROR", error.ts)) == 384
    assert len(await stored_embedding(run_id, "CRITICAL", critical.ts)) == 384
    assert await stored_embedding(run_id, "CRITICAL", error.ts) is None
    assert await queued(run_id) == []


async def test_a_repeated_message_in_a_run_is_marked_duplicate(processor, sct_service, run_id):
    now = datetime.now(tz=UTC).timestamp()
    first = await _submit(sct_service, run_id, "ERROR", STALL, now)
    repeat = await _submit(sct_service, run_id, "ERROR", STALL, now + 1)

    await processor.process([first, repeat])

    events = {event["ts"]: event for event in await stored_events(run_id)}
    [first_event, repeat_event] = sorted(events.values(), key=lambda event: event["ts"])
    assert first_event["duplicate_id"] is None
    assert repeat_event["duplicate_id"] == first_event["event_id"]
    assert await stored_embedding(run_id, "ERROR", first.ts) is not None
    assert await stored_embedding(run_id, "ERROR", repeat.ts) is None
    assert await queued(run_id) == []


async def test_the_same_message_in_another_run_is_unique(processor, sct_service, client_service, fake_test, run_id):
    other_run_id = await submitted_run(client_service, fake_test)
    first = await _submit(sct_service, other_run_id, "ERROR", STALL)
    second = await _submit(sct_service, run_id, "ERROR", STALL)

    await processor.process([first, second])

    [event] = await stored_events(run_id)
    assert event["duplicate_id"] is None
    assert await stored_embedding(run_id, "ERROR", second.ts) is not None


async def test_an_event_whose_message_sanitizes_to_nothing_is_dequeued(processor, sct_service, run_id):
    event = await _submit(sct_service, run_id, "ERROR", "0x1234")

    await processor.process([event])

    assert await stored_embedding(run_id, "ERROR", event.ts) is None
    assert await queued(run_id) == []


async def test_a_failing_embedder_keeps_the_queue_row(processor, sct_service, run_id, monkeypatch):
    def unavailable(texts):
        raise RuntimeError("model download failed")

    monkeypatch.setattr(processor._embedder, "model", unavailable)
    event = await _submit(sct_service, run_id, "ERROR", STALL)

    await processor.process([event])

    assert await stored_embedding(run_id, "ERROR", event.ts) is None
    assert len(await queued(run_id)) == 1


async def test_reprocessing_an_event_does_not_mark_it_a_duplicate_of_itself(processor, sct_service, run_id):
    event = await _submit(sct_service, run_id, "ERROR", STALL)

    await processor.process([event])
    await processor.process([event])

    [stored] = await stored_events(run_id)
    assert stored["duplicate_id"] is None
    assert await stored_embedding(run_id, "ERROR", event.ts) is not None


async def test_the_sweep_takes_old_rows_and_leaves_fresh_ones(processor, sct_service, client_service, fake_test,
                                                              run_id):
    fresh_run_id = await submitted_run(client_service, fake_test)
    await _submit(sct_service, fresh_run_id, "ERROR", STALL)
    legacy = await _submit(sct_service, run_id, "ERROR", STALL)
    legacy_row = SCTUnprocessedEvent.model_construct()
    legacy_row.run_id, legacy_row.severity, legacy_row.ts, legacy_row.queued_at = (
        legacy.run_id, legacy.severity, legacy.ts, None)
    await legacy_row.save()

    processed = await processor.sweep(timedelta(minutes=10))

    assert processed >= 1
    assert await stored_embedding(run_id, "ERROR", legacy.ts) is not None
    assert await queued(run_id) == []
    assert len(await queued(fresh_run_id)) == 1

    await processor.sweep(timedelta(0))

    assert await queued(fresh_run_id) == []


async def test_events_of_other_severities_are_not_queued(sct_service, run_id):
    for severity in (SCTEventSeverity.WARNING.value, SCTEventSeverity.NORMAL.value):
        await sct_service.submit_event(run_id, event_payload(run_id, severity, STALL))

    assert await queued(run_id) == []
