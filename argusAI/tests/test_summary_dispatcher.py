"""Unit tests for SummaryDispatcher (best-effort event summarization).

The OpenAI client is mocked; there is no network and no real ScyllaDB — the "db" is a fake
that records the CQL it was asked to execute. Covers the behaviors the design requires
(docs/plans/event-summarization.md §8): unique event -> UPDATE with the right key, disabled
/ keyless -> inert, summarizer error -> no write, and the min-tokens gate.
"""

import threading
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from argusAI.utils import summary_dispatcher as sd
from argusAI.utils.summarizer import SummarizationResult, SummarizerError


class FakeDB:
    def __init__(self, config):
        self.config = config
        self.executed = []

    def execute(self, query, params):
        self.executed.append((query, params))
        return object()  # real ScyllaConnection.execute returns a truthy ResultSet on success


class FakeSummarizer:
    """Stands in for argusAI.utils.summarizer.Summarizer."""

    instances = []

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
        "OPENAI_API_KEY": "test-key",
        "OPENAI_SUMMARY_MODEL": "gpt-5-mini",
        "EVENT_SUMMARIZATION_MAX_CONCURRENCY": 2,
        "EVENT_SUMMARIZATION_MIN_TOKENS": 0,  # gate off by default; the gate test opts in
    }
    cfg.update(over)
    return cfg


def _dispatch_one(dispatcher, message="a fairly long event message with detail"):
    run_id, ts = uuid4(), datetime.now(timezone.utc)
    dispatcher.dispatch(run_id, "ERROR", ts, message)
    dispatcher.shutdown()  # drains in-flight tasks
    return run_id, ts


def test_unique_event_writes_summary_with_right_key(monkeypatch):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    db = FakeDB(_config())
    dispatcher = sd.SummaryDispatcher(db, db.config)
    assert dispatcher.enabled

    run_id, ts = _dispatch_one(dispatcher, "database error: sstable corruption at offset 42")

    assert len(db.executed) == 1
    query, params = db.executed[0]
    assert "UPDATE sct_event SET summary" in query
    assert "WHERE run_id = ? AND severity = ? AND ts = ?" in query
    summary, w_run, w_sev, w_ts = params
    assert w_run == run_id and w_sev == "ERROR" and w_ts == ts
    assert summary.startswith("SUMMARY[")


def test_disabled_is_inert(monkeypatch):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    db = FakeDB(_config(EVENT_SUMMARIZATION_ENABLED=False))
    dispatcher = sd.SummaryDispatcher(db, db.config)
    assert not dispatcher.enabled
    _dispatch_one(dispatcher)
    assert db.executed == []
    assert FakeSummarizer.instances == []  # no client constructed


def test_missing_key_disables_without_crashing(monkeypatch):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    db = FakeDB(_config(OPENAI_API_KEY=None))
    dispatcher = sd.SummaryDispatcher(db, db.config)
    assert not dispatcher.enabled
    _dispatch_one(dispatcher)
    assert db.executed == []


def test_summarizer_error_leaves_summary_null(monkeypatch):
    monkeypatch.setattr(sd, "Summarizer", ErroringSummarizer)
    db = FakeDB(_config())
    dispatcher = sd.SummaryDispatcher(db, db.config)
    _dispatch_one(dispatcher)
    assert db.executed == []  # failure => no write, summary stays null


def test_min_tokens_gate_skips_short_events(monkeypatch):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    db = FakeDB(_config(EVENT_SUMMARIZATION_MIN_TOKENS=50))
    dispatcher = sd.SummaryDispatcher(db, db.config)

    _dispatch_one(dispatcher, "short message")  # ~2 tokens, below threshold
    assert db.executed == []

    dispatcher2 = sd.SummaryDispatcher(db, db.config)
    long_message = "sstable corruption detected at offset during compaction on node ram-0 " * 10
    _dispatch_one(dispatcher2, long_message)  # ~100 tokens, above threshold
    assert len(db.executed) == 1


def test_empty_message_not_dispatched(monkeypatch):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    db = FakeDB(_config())
    dispatcher = sd.SummaryDispatcher(db, db.config)
    _dispatch_one(dispatcher, "")
    assert db.executed == []


def test_malformed_config_disables_without_crashing(monkeypatch):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    db = FakeDB(_config(EVENT_SUMMARIZATION_MIN_TOKENS="not-a-number"))
    dispatcher = sd.SummaryDispatcher(db, db.config)  # int() must not escape __init__
    assert not dispatcher.enabled
    _dispatch_one(dispatcher)
    assert db.executed == []


def test_dispatch_swallows_submit_failure_and_releases_slot(monkeypatch):
    """A submit failure (e.g. executor shut down) must never propagate into the embedding
    path, and the acquired slot must be released so summarization is not wedged forever."""
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    db = FakeDB(_config(EVENT_SUMMARIZATION_MAX_CONCURRENCY=1, EVENT_SUMMARIZATION_MAX_BACKLOG=4))
    dispatcher = sd.SummaryDispatcher(db, db.config)

    class BoomExecutor:
        def submit(self, *args, **kwargs):
            raise RuntimeError("cannot schedule new futures after shutdown")

    dispatcher._executor = BoomExecutor()

    for _ in range(10):  # more than the 4 slots -> proves the slot is released each time
        dispatcher.dispatch(uuid4(), "ERROR", datetime.now(timezone.utc), "long enough message")

    assert db.executed == []
    assert dispatcher._slots.acquire(blocking=False)  # a slot is still free, not leaked


def test_counters_track_success(monkeypatch):
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    db = FakeDB(_config())
    dispatcher = sd.SummaryDispatcher(db, db.config)
    _dispatch_one(dispatcher, "a sufficiently long event message worth summarizing")
    assert (dispatcher._n_ok, dispatcher._n_failed, dispatcher._n_dropped) == (1, 0, 0)


def test_counters_track_failure(monkeypatch):
    monkeypatch.setattr(sd, "Summarizer", ErroringSummarizer)
    db = FakeDB(_config())
    dispatcher = sd.SummaryDispatcher(db, db.config)
    _dispatch_one(dispatcher, "a sufficiently long event message worth summarizing")
    assert (dispatcher._n_ok, dispatcher._n_failed, dispatcher._n_dropped) == (0, 1, 0)


def test_swallowed_db_write_counts_as_failure(monkeypatch):
    # ScyllaConnection.execute swallows write errors and returns None; a null result must
    # be treated as a failed persist, not logged/counted as a success.
    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)

    class SwallowingDB(FakeDB):
        def execute(self, query, params):
            self.executed.append((query, params))  # records the write, then returns None like a swallowed failure

    db = SwallowingDB(_config())
    dispatcher = sd.SummaryDispatcher(db, db.config)
    _dispatch_one(dispatcher, "a sufficiently long event message worth summarizing")
    assert (dispatcher._n_ok, dispatcher._n_failed, dispatcher._n_dropped) == (0, 1, 0)


def test_backlog_full_is_dropped(monkeypatch):
    gate = threading.Event()

    class BlockingSummarizer(FakeSummarizer):
        def summarize(self, model, message, prompt=None, **kwargs):
            gate.wait(timeout=5)  # hold the slot until released
            return super().summarize(model, message, prompt, **kwargs)

    monkeypatch.setattr(sd, "Summarizer", BlockingSummarizer)
    db = FakeDB(_config(EVENT_SUMMARIZATION_MAX_CONCURRENCY=1, EVENT_SUMMARIZATION_MAX_BACKLOG=4))
    dispatcher = sd.SummaryDispatcher(db, db.config)
    msg = "an event message long enough to pass the gate"

    for _ in range(4):  # fill every slot (tasks block, holding them)
        dispatcher.dispatch(uuid4(), "ERROR", datetime.now(timezone.utc), msg)
    dispatcher.dispatch(uuid4(), "ERROR", datetime.now(timezone.utc), msg)  # no slot -> dropped

    gate.set()
    dispatcher._executor.shutdown(wait=True)  # drain the 4 accepted tasks (no cancellation)
    assert len(db.executed) == 4
