"""Tests for SummaryDispatcher: best-effort summaries of unique events.

The Anthropic client is a fake; the events and the summaries live in the test database.
"""

import threading
from datetime import UTC, datetime
from uuid import UUID

import pytest

from argus.backend.plugins.sct.events import summary_dispatcher as sd
from argus.backend.plugins.sct.events.summarizer import SummarizationResult, SummarizerError
from argus.backend.plugins.sct.events.summary_dispatcher import SummaryDispatcher, UniqueEvent
from argus.backend.plugins.sct.service import SCTService
from argus.backend.service.client_service import ClientService
from argus.backend.tests.sct_events.helpers import event_payload, stored_events, submitted_run

LONG_MESSAGE = "database error: sstable corruption at offset 42 during compaction on node ram-0 " * 3


class FakeSummarizer:
    instances: list["FakeSummarizer"] = []

    def __init__(self, *args, **kwargs):
        self.calls = []
        FakeSummarizer.instances.append(self)

    def summarize(self, model, message, prompt=None, **kwargs):
        self.calls.append((model, message, prompt))
        return SummarizationResult(
            summary=f"SUMMARY[{message[:10]}]",
            model=model,
            prompt_tokens=100,
            completion_tokens=20,
            cached_tokens=0,
            latency_ms=5.0,
        )


class ErroringSummarizer(FakeSummarizer):
    def summarize(self, model, message, prompt=None, **kwargs):
        raise SummarizerError("boom")


@pytest.fixture(autouse=True)
def _reset():
    FakeSummarizer.instances = []


def _config(**over):
    cfg = {
        "EVENT_SUMMARIZATION_ENABLED": True,
        "ANTHROPIC_API_KEY": "test-key",
        "ANTHROPIC_SUMMARY_MODEL": "claude-sonnet-5",
        "EVENT_SUMMARIZATION_MAX_CONCURRENCY": 2,
        "EVENT_SUMMARIZATION_MIN_TOKENS": 0,
    }
    cfg.update(over)
    return cfg


async def _stored_event(client_service: ClientService, sct_service: SCTService, fake_test,
                        message: str = LONG_MESSAGE) -> UniqueEvent:
    run_id = await submitted_run(client_service, fake_test)
    payload = event_payload(run_id, "ERROR", message)
    await sct_service.submit_event(run_id, payload)
    return UniqueEvent(run_id=run_id, severity="ERROR", ts=datetime.fromtimestamp(payload["ts"], tz=UTC),
                       message=message)


async def _summary(run_id: UUID) -> str | None:
    [event] = await stored_events(run_id)
    return event["summary"]


@pytest.fixture
async def event(client_service, sct_service, fake_test) -> UniqueEvent:
    return await _stored_event(client_service, sct_service, fake_test)


async def test_writes_the_summary_of_a_unique_event(monkeypatch, event):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    dispatcher = SummaryDispatcher(_config())
    assert dispatcher.enabled

    await dispatcher.summarize([event])

    assert await _summary(event.run_id) == f"SUMMARY[{LONG_MESSAGE[:10]}]"
    assert (dispatcher._n_ok, dispatcher._n_failed, dispatcher._n_dropped) == (1, 0, 0)


@pytest.mark.parametrize("config", [
    _config(EVENT_SUMMARIZATION_ENABLED=False),
    _config(ANTHROPIC_API_KEY=None),
    _config(EVENT_SUMMARIZATION_MIN_TOKENS="not-a-number"),
], ids=["disabled", "no-key", "malformed"])
async def test_an_unusable_config_leaves_the_dispatcher_inert(monkeypatch, event, config):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    dispatcher = SummaryDispatcher(config)

    await dispatcher.summarize([event])

    assert not dispatcher.enabled
    assert all(not instance.calls for instance in FakeSummarizer.instances)
    assert await _summary(event.run_id) is None


async def test_a_summarizer_error_leaves_the_summary_null(monkeypatch, event):
    monkeypatch.setattr(sd, "Summarizer", ErroringSummarizer)
    dispatcher = SummaryDispatcher(_config())

    await dispatcher.summarize([event])

    assert await _summary(event.run_id) is None
    assert (dispatcher._n_ok, dispatcher._n_failed, dispatcher._n_dropped) == (0, 1, 0)


async def test_the_min_token_gate_skips_short_events(monkeypatch, client_service, sct_service, fake_test):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    dispatcher = SummaryDispatcher(_config(EVENT_SUMMARIZATION_MIN_TOKENS=50))
    short = await _stored_event(client_service, sct_service, fake_test, "short message")
    long = await _stored_event(client_service, sct_service, fake_test)

    await dispatcher.summarize([short, long])

    assert await _summary(short.run_id) is None
    assert await _summary(long.run_id) is not None


async def test_an_empty_message_is_not_summarized(monkeypatch, event):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    dispatcher = SummaryDispatcher(_config())

    await dispatcher.summarize([UniqueEvent(event.run_id, event.severity, event.ts, "")])

    assert FakeSummarizer.instances[0].calls == []


async def test_events_past_the_backlog_are_dropped(monkeypatch, client_service, sct_service, fake_test):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    dispatcher = SummaryDispatcher(_config(EVENT_SUMMARIZATION_MAX_CONCURRENCY=1,
                                           EVENT_SUMMARIZATION_MAX_BACKLOG=2))
    events = [await _stored_event(client_service, sct_service, fake_test) for _ in range(3)]

    await dispatcher.summarize(events)

    assert [await _summary(event.run_id) is not None for event in events] == [True, True, False]
    assert (dispatcher._n_ok, dispatcher._n_failed, dispatcher._n_dropped) == (2, 0, 1)


async def test_concurrency_stays_within_the_limit(monkeypatch, client_service, sct_service, fake_test):
    lock = threading.Lock()
    running = 0
    peak = 0

    class CountingSummarizer(FakeSummarizer):
        def summarize(self, model, message, prompt=None, **kwargs):
            nonlocal running, peak
            with lock:
                running += 1
                peak = max(peak, running)
            threading.Event().wait(0.05)
            with lock:
                running -= 1
            return super().summarize(model, message, prompt, **kwargs)

    monkeypatch.setattr(sd, "Summarizer", CountingSummarizer)
    dispatcher = SummaryDispatcher(_config(EVENT_SUMMARIZATION_MAX_CONCURRENCY=2))
    events = [await _stored_event(client_service, sct_service, fake_test) for _ in range(5)]

    await dispatcher.summarize(events)

    assert peak == 2
    assert dispatcher._n_ok == 5


async def test_the_encoder_loads_on_the_first_summary_and_a_failed_load_skips_it(monkeypatch, event):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    loads = []

    def unavailable():
        loads.append(True)
        raise OSError("encoding download failed")

    monkeypatch.setattr(sd, "_resolve_encoder", unavailable)
    dispatcher = SummaryDispatcher(_config())
    assert loads == []

    await dispatcher.summarize([event])

    assert loads == [True]
    assert await _summary(event.run_id) is None
    assert (dispatcher._n_ok, dispatcher._n_failed, dispatcher._n_dropped) == (0, 1, 0)
