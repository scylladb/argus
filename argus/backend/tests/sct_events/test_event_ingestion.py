import asyncio
import datetime
import logging
import time
from uuid import UUID, uuid4

import pytest
from click.testing import CliRunner
from starlette.testclient import TestClient

from argus.backend.cli import process_event_queue_command

from argus.backend.plugins.sct.events import summary_dispatcher as sd
from argus.backend.plugins.sct.events.processor import get_event_processor
from argus.backend.plugins.sct.events.summarizer import SummarizationResult
from argus.backend.plugins.sct.events.summary_dispatcher import SummaryDispatcher
from argus.backend.tests.util import StubEmbeddingModel
from argus.backend.tests.sct_events.helpers import queued, stored_embedding
from argus.common.utils import clamp_ts_to_milliseconds

API_PREFIX = "/api/v1/client/sct"


@pytest.fixture
def sct_run_id(api_client, fake_test) -> str:
    run_id = str(uuid4())
    resp = api_client.post("/api/v1/client/testrun/scylla-cluster-tests/submit", json={
        "run_id": run_id,
        "job_name": fake_test.build_system_id,
        "job_url": "http://example.com/job/1",
        "started_by": "test_user",
        "commit_id": "deadbeef",
        "origin_url": "http://example.com/repo.git",
        "branch_name": "main",
        "sct_config": {"cluster_backend": "aws"},
        "schema_version": "v8",
    })
    assert resp.status_code == 200, resp.text
    return run_id


def _event(run_id: str, severity: str, message: str, ts: float) -> dict:
    return {"run_id": run_id, "severity": severity, "ts": ts, "message": message, "event_type": "DatabaseLogEvent"}


def _submit(api_client, run_id: str, events: list[dict]) -> None:
    resp = api_client.post(f"{API_PREFIX}/{run_id}/event/submit", json={"data": events, "schema_version": "v8"})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok", "response": True}


def _events(api_client, run_id: str) -> list[dict]:
    resp = api_client.get(f"{API_PREFIX}/{run_id}/events/get")
    assert resp.status_code == 200, resp.text
    return resp.json()["response"]


def _now() -> float:
    return clamp_ts_to_milliseconds(datetime.datetime.now(tz=datetime.UTC).timestamp())


def _dt(ts: float) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(ts, tz=datetime.UTC)


async def test_a_submitted_error_event_has_its_embedding_after_the_response(api_client, sct_run_id):
    ts = _now()

    _submit(api_client, sct_run_id, [_event(sct_run_id, "ERROR", "Reactor stalled for 512 ms", ts)])

    assert await stored_embedding(UUID(sct_run_id), "ERROR", _dt(ts)) is not None
    assert await queued(UUID(sct_run_id)) == []


async def test_a_repeated_message_in_one_submission_is_marked_duplicate(api_client, sct_run_id):
    ts = _now()
    message = "Scylla process aborted on node-2"

    _submit(api_client, sct_run_id, [
        _event(sct_run_id, "CRITICAL", message, ts),
        _event(sct_run_id, "CRITICAL", message, ts + 1),
    ])

    first, repeat = sorted(_events(api_client, sct_run_id), key=lambda event: event["ts"])
    assert first["duplicate_id"] is None
    assert repeat["duplicate_id"] == first["event_id"]


async def test_the_submit_succeeds_and_the_row_stays_when_the_model_fails(api_client, sct_run_id, monkeypatch):
    def unavailable(texts):
        raise RuntimeError("model download failed")

    monkeypatch.setattr(get_event_processor()._embedder, "model", unavailable)
    ts = _now()

    _submit(api_client, sct_run_id, [_event(sct_run_id, "ERROR", "Reactor stalled for 512 ms", ts)])

    assert [event["message"] for event in _events(api_client, sct_run_id)] == ["Reactor stalled for 512 ms"]
    assert await stored_embedding(UUID(sct_run_id), "ERROR", _dt(ts)) is None
    assert len(await queued(UUID(sct_run_id))) == 1


async def test_a_unique_event_gets_a_summary_when_summarization_is_on(api_client, sct_run_id, monkeypatch):
    class FakeSummarizer:
        def __init__(self, *args, **kwargs):
            pass

        def summarize(self, model, message, prompt=None, **kwargs):
            return SummarizationResult(summary=f"summary of {message}", model=model, prompt_tokens=10,
                                       completion_tokens=5, cached_tokens=0, latency_ms=1.0)

    monkeypatch.setattr(sd, "Summarizer", FakeSummarizer)
    monkeypatch.setattr(get_event_processor(), "_dispatcher", SummaryDispatcher({
        "EVENT_SUMMARIZATION_ENABLED": True,
        "ANTHROPIC_API_KEY": "test-key",
        "EVENT_SUMMARIZATION_MIN_TOKENS": 0,
    }))
    message = "database error: sstable corruption at offset 42"

    _submit(api_client, sct_run_id, [_event(sct_run_id, "ERROR", message, _now())])

    [event] = _events(api_client, sct_run_id)
    assert event["summary"] == f"summary of {message}"
    assert event["message"] == message


def test_the_sweep_command_processes_a_row_a_failed_task_left(api_client, sct_run_id, monkeypatch):
    processor = get_event_processor()
    model = processor._embedder.model

    def unavailable(texts):
        raise RuntimeError("model download failed")

    monkeypatch.setattr(processor._embedder, "model", unavailable)
    ts = _now()
    _submit(api_client, sct_run_id, [_event(sct_run_id, "ERROR", "Reactor stalled for 512 ms", ts)])
    monkeypatch.setattr(processor._embedder, "model", model)

    logging.disable(logging.CRITICAL)
    try:
        result = CliRunner().invoke(process_event_queue_command, ["--min-age", "0"], catch_exceptions=False)
    finally:
        logging.disable(logging.NOTSET)

    assert result.exit_code == 0, result.output
    assert asyncio.run(stored_embedding(UUID(sct_run_id), "ERROR", _dt(ts))) is not None
    assert asyncio.run(queued(UUID(sct_run_id))) == []


def test_the_app_builds_the_processor_and_loads_the_model_at_startup(asgi_app, monkeypatch):
    loads = []
    monkeypatch.setattr(StubEmbeddingModel, "load", lambda self: loads.append(self))
    get_event_processor.cache_clear()

    with TestClient(asgi_app):
        deadline = time.monotonic() + 10
        while not loads and time.monotonic() < deadline:
            time.sleep(0.05)

    assert get_event_processor.cache_info().currsize == 1
    assert loads == [get_event_processor()._embedder.model]


def test_a_batch_with_a_bad_event_still_processes_the_events_it_stored(asgi_app, api_client, sct_run_id):
    ts = _now()
    events = [_event(sct_run_id, "ERROR", "Reactor stalled for 512 ms", ts),
              _event(sct_run_id, "NOT-A-SEVERITY", "broken", ts + 1)]

    with TestClient(asgi_app, raise_server_exceptions=False) as client:
        resp = client.post(f"{API_PREFIX}/{sct_run_id}/event/submit", json={"data": events, "schema_version": "v8"})

    assert resp.json()["status"] == "error"
    assert asyncio.run(stored_embedding(UUID(sct_run_id), "ERROR", _dt(ts))) is not None
    assert asyncio.run(queued(UUID(sct_run_id))) == []
