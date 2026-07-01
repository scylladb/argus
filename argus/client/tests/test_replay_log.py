"""Tests for the JSONL Argus replay log."""
import gc
import json
import logging
import threading
import time
import weakref
from uuid import uuid4

import pytest

from argus.client.base import ArgusClient
from argus.client.replay_log import ReplayLog


def _read_records(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class _RaisingFile:
    """Fake file-like object whose write() always raises OSError."""

    closed = False

    def write(self, _line):
        raise OSError("simulated disk failure")

    def flush(self):
        pass

    def close(self):
        self.closed = True


def test_replay_log_writes_preflight_and_final_record_per_call(tmp_path):
    log = ReplayLog(log_dir=tmp_path, run_id="run-1", test_type="generic")
    with log.record("POST", "/foo/$id", {"id": "abc"}, None, {"k": "v"}) as rec:
        rec.success = True
    log.close()

    records = _read_records(log.path)
    assert len(records) == 2

    preflight, final = records
    assert preflight["phase"] == "pending"
    assert preflight["success"] is False
    assert "error" not in preflight
    assert final["phase"] == "final"
    assert final["success"] is True

    for r in records:
        assert r["method"] == "POST"
        assert r["endpoint"] == "/foo/$id"
        assert r["location_params"] == {"id": "abc"}
        assert r["params"] is None
        assert r["body"] == {"k": "v"}
        assert r["test_type"] == "generic"
        assert isinstance(r["ts"], int)


def test_replay_log_persists_preflight_entry_before_http_call_runs(tmp_path):
    # Major-issue #3: even if the process is killed mid-call, the intended
    # request must already be durable on disk before any HTTP call is made.
    log = ReplayLog(log_dir=tmp_path, run_id="run-1", test_type="generic")
    with log.record("POST", "/foo", None, None, {"k": "v"}) as rec:
        on_disk = _read_records(log.path)
        assert len(on_disk) == 1
        assert on_disk[0]["phase"] == "pending"
        assert on_disk[0]["success"] is False
        assert on_disk[0]["body"] == {"k": "v"}
        rec.success = True
    log.close()

    assert len(_read_records(log.path)) == 2


def test_replay_log_round_trips_non_none_params(tmp_path):
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    location_params = {"id": "abc", "kind": "sct"}
    query_params = {"limit": 50, "active": True}
    body = {"nested": {"a": [1, 2, 3]}, "name": "x"}
    with log.record("POST", "/foo/$id", location_params, query_params, body) as rec:
        rec.success = True
    log.close()

    records = _read_records(log.path)
    assert len(records) == 2
    for r in records:
        assert r["location_params"] == location_params
        assert r["params"] == query_params
        assert r["body"] == body


def test_replay_log_captures_exception_as_error(tmp_path):
    log = ReplayLog(log_dir=tmp_path, run_id="run-1", test_type="generic")
    with pytest.raises(RuntimeError):
        with log.record("POST", "/foo", None, None, {}) as rec:
            raise RuntimeError("boom")
    log.close()

    records = _read_records(log.path)
    assert len(records) == 2
    assert records[0]["phase"] == "pending"
    assert records[0]["success"] is False
    assert "error" not in records[0]
    assert records[1]["phase"] == "final"
    assert records[1]["success"] is False
    assert records[1]["error"].startswith("RuntimeError: boom")


def test_replay_log_filename_includes_run_id_and_ts(tmp_path):
    log = ReplayLog(log_dir=tmp_path, run_id="abc-123", test_type="t")
    log.close()
    assert log.path.name.startswith("argus_replay_log_abc-123_")
    assert log.path.name.endswith(".jsonl")


def test_replay_log_sanitizes_run_id_in_filename(tmp_path):
    log = ReplayLog(log_dir=tmp_path, run_id="../../etc/passwd", test_type="t")
    log.close()
    assert log.path.parent == tmp_path
    assert "/" not in log.path.name
    assert ".." not in log.path.name


def test_replay_log_uses_unknown_when_run_id_missing(tmp_path):
    log = ReplayLog(log_dir=tmp_path, run_id=None, test_type="t")
    log.close()
    assert "unknown" in log.path.name


def test_replay_log_creates_log_dir_if_missing(tmp_path):
    target = tmp_path / "nested" / "dir"
    log = ReplayLog(log_dir=target, run_id="r", test_type="t")
    log.close()
    assert target.exists()
    assert log.path.parent == target


def test_replay_log_works_as_context_manager(tmp_path):
    with ReplayLog(log_dir=tmp_path, run_id="r", test_type="t") as log:
        with log.record("POST", "/x", None, None, {}) as rec:
            rec.success = True
        path = log.path
    assert _read_records(path)[-1]["success"] is True


def test_replay_log_is_thread_safe(tmp_path):
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")

    n_threads = 16
    per_thread = 50

    def worker(tid):
        for i in range(per_thread):
            with log.record("POST", "/x", None, None, {"tid": tid, "i": i}) as rec:
                rec.success = True

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log.close()

    records = _read_records(log.path)
    # Each call writes a pre-flight + a final record.
    assert len(records) == n_threads * per_thread * 2
    # No partial lines / no JSON corruption.
    finals = [r for r in records if r["success"] is True]
    seen = {(r["body"]["tid"], r["body"]["i"]) for r in finals}
    assert len(finals) == n_threads * per_thread
    assert len(seen) == n_threads * per_thread


def test_replay_log_multiple_instances_same_run_id_no_interference(tmp_path):
    log_a = ReplayLog(log_dir=tmp_path, run_id="same", test_type="t")
    log_b = ReplayLog(log_dir=tmp_path, run_id="same", test_type="t")
    with log_a.record("POST", "/a", None, None, {"who": "a"}):
        pass
    with log_b.record("POST", "/b", None, None, {"who": "b"}):
        pass
    log_a.close()
    log_b.close()

    assert log_a.path != log_b.path
    assert _read_records(log_a.path)[0]["body"] == {"who": "a"}
    assert _read_records(log_b.path)[0]["body"] == {"who": "b"}


def test_replay_log_uses_compact_json_separators(tmp_path):
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    with log.record("POST", "/x", None, None, {"a": 1, "b": 2}):
        pass
    log.close()
    raw = log.path.read_text()
    # No ", " or ": " spacing -- compact JSON.
    assert ", " not in raw
    assert ": " not in raw


def test_replay_log_close_is_idempotent(tmp_path):
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    log.close()
    log.close()


def test_replay_log_record_after_close_does_not_raise_and_still_runs_http_call(tmp_path):
    # A closed/broken replay log must never block or fail the caller's real
    # request -- it should just stop being recorded.
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    log.close()

    ran = False
    with log.record("POST", "/x", None, None, {}) as rec:
        ran = True
        rec.success = True
    assert ran is True
    # Nothing should have been written -- the file is already closed.
    assert _read_records(log.path) == []


def test_replay_log_close_waits_for_in_flight_record(tmp_path):
    # Major-issue #2: close() must not drop a request that is still
    # in-flight (already past the "is this closed" check) when it is called.
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    entered = threading.Event()
    finish = threading.Event()
    result = {}

    def worker():
        with log.record("POST", "/slow", None, None, {}) as rec:
            entered.set()
            finish.wait(timeout=5.0)
            rec.success = True
        result["done"] = True

    t = threading.Thread(target=worker)
    t.start()
    assert entered.wait(timeout=5.0)

    def release_after_delay():
        time.sleep(0.05)
        finish.set()

    threading.Thread(target=release_after_delay).start()
    log.close(timeout=5.0)
    t.join(timeout=5.0)

    assert result.get("done") is True
    records = _read_records(log.path)
    assert len(records) == 2
    assert records[-1]["success"] is True


def test_replay_log_close_timeout_logs_which_record_is_dropped(tmp_path, caplog):
    # If close() times out with a request still running, the eventual final
    # write is dropped -- but it must be logged with enough detail (method +
    # endpoint) to identify what was lost, not just a bare count.
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    entered = threading.Event()
    finish = threading.Event()

    def worker():
        with log.record("POST", "/slow-endpoint", None, None, {}) as rec:
            entered.set()
            finish.wait(timeout=5.0)
            rec.success = True

    t = threading.Thread(target=worker)
    t.start()
    assert entered.wait(timeout=5.0)

    with caplog.at_level(logging.WARNING, logger="argus.client.replay_log"):
        log.close(timeout=0.01)
        assert any("in-flight" in r.message for r in caplog.records)

        # The worker's final write happens after close() already gave up and
        # closed the file -- that drop must be logged, identifying the request.
        finish.set()
        t.join(timeout=5.0)
        assert any(
            "/slow-endpoint" in r.message and "POST" in r.message for r in caplog.records
        )


def test_replay_log_write_failure_does_not_raise_or_leak_active_count(tmp_path):
    # Major-issue #4: a writer failure (e.g. ENOSPC/permission error) must
    # not propagate into the caller, and there is no queue to leak memory in.
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    log._file.close()
    log._file = _RaisingFile()

    with log.record("POST", "/x", None, None, {}) as rec:
        rec.success = True

    assert log._active == 0
    assert log._closed is False
    log.close()


def test_replay_log_pre_flight_serialization_failure_does_not_block_http_call(tmp_path):
    # A body that can't be JSON-serialized (even with default=str) must not
    # prevent the caller's real HTTP call from running.
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    circular = {}
    circular["self"] = circular

    ran = False
    with log.record("POST", "/x", None, None, circular) as rec:
        ran = True
        rec.success = True
    assert ran is True
    log.close()


def test_replay_log_survives_unwritable_log_dir(tmp_path):
    # A bad log_dir (here: a path component that is a plain file, so mkdir
    # can never succeed) must not prevent construction, recording, or
    # closing -- it should just run without persisting anything.
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    bad_log_dir = blocked / "nested"

    log = ReplayLog(log_dir=bad_log_dir, run_id="r", test_type="t")
    ran = False
    with log.record("POST", "/x", None, None, {}) as rec:
        ran = True
        rec.success = True
    assert ran is True
    log.close()


def test_replay_log_close_does_not_raise_when_file_close_fails(tmp_path, monkeypatch):
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")

    def raise_on_close():
        raise OSError("simulated close failure")

    monkeypatch.setattr(log._file, "close", raise_on_close)
    log.close()  # must not raise
    assert log._closed is True


def test_replay_log_can_be_garbage_collected_without_explicit_close(tmp_path):
    # atexit registration must use a weak reference so a caller that forgets
    # close() doesn't leak the instance (and its open file handle) for the
    # rest of the process lifetime.
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    ref = weakref.ref(log)
    del log
    gc.collect()
    assert ref() is None


def test_replay_log_atexit_callback_noops_after_garbage_collection(tmp_path):
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    ref = weakref.ref(log)
    callback = log._atexit_callback
    del log
    gc.collect()
    callback()  # must not raise even though the referent is gone
    assert ref() is None


def test_replay_log_close_only_unregisters_its_own_atexit_callback(tmp_path, monkeypatch):
    # atexit.unregister() matches by function identity and ignores
    # arguments -- if every instance registered the same shared
    # staticmethod, closing one instance would silently unregister the
    # atexit safety net for every other still-open instance too. Each
    # instance must register (and later unregister) a distinct callable.
    import atexit as atexit_module

    registered = []
    unregistered = []
    real_register = atexit_module.register
    real_unregister = atexit_module.unregister

    def fake_register(fn, *args, **kwargs):
        registered.append(fn)
        return real_register(fn, *args, **kwargs)

    def fake_unregister(fn):
        unregistered.append(fn)
        return real_unregister(fn)

    monkeypatch.setattr(atexit_module, "register", fake_register)
    monkeypatch.setattr(atexit_module, "unregister", fake_unregister)

    log_a = ReplayLog(log_dir=tmp_path, run_id="a", test_type="t")
    log_b = ReplayLog(log_dir=tmp_path, run_id="b", test_type="t")
    assert log_a._atexit_callback is not log_b._atexit_callback
    assert registered == [log_a._atexit_callback, log_b._atexit_callback]

    log_a.close()
    assert unregistered == [log_a._atexit_callback]

    log_b.close()
    assert unregistered == [log_a._atexit_callback, log_b._atexit_callback]


def test_replay_record_uses_response_ok_gate(tmp_path):
    # response.ok is True for any status < 400 (so 3xx passes the gate here,
    # unlike a strict 200-299 check) -- a JSON body still has to say "ok".
    class _FakeResponse:
        status_code = 302
        ok = True

        def json(self):
            return {"status": "ok"}

    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    with log.record("POST", "/x", None, None, {}) as rec:
        rec.record(_FakeResponse())
    log.close()

    assert _read_records(log.path)[-1]["success"] is True


def test_replay_record_treats_4xx_5xx_as_failure(tmp_path):
    class _FakeResponse:
        status_code = 404
        ok = False

        def json(self):
            return {"status": "ok"}

    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    with log.record("POST", "/x", None, None, {}) as rec:
        rec.record(_FakeResponse())
    log.close()

    assert _read_records(log.path)[-1]["success"] is False
    assert _read_records(log.path)[-1]["error"] == "HTTP 404"


def test_argus_client_post_writes_replay_record(requests_mock, tmp_path):
    requests_mock.post(
        "https://test.example.com/api/v1/client/testrun/test-type/submit",
        json={"status": "ok"},
        status_code=200,
    )
    client = ArgusClient(
        auth_token="t",
        base_url="https://test.example.com",
        log_dir=tmp_path,
    )
    client.post(
        endpoint=ArgusClient.Routes.SUBMIT,
        location_params={"type": "test-type"},
        body={"hello": "world"},
    )
    client.close()

    records = _read_records(client.replay_log_path)
    assert len(records) == 2
    for r in records:
        assert r["endpoint"] == ArgusClient.Routes.SUBMIT
        assert r["location_params"] == {"type": "test-type"}
        assert r["body"] == {"hello": "world"}
    assert records[0]["success"] is False
    assert records[1]["success"] is True


def test_argus_client_post_records_failure_on_non_2xx(requests_mock, tmp_path):
    requests_mock.post(
        "https://test.example.com/api/v1/client/testrun/test-type/submit",
        json={"error": "boom"},
        status_code=500,
    )
    client = ArgusClient(
        auth_token="t",
        base_url="https://test.example.com",
        log_dir=tmp_path,
    )
    client.post(
        endpoint=ArgusClient.Routes.SUBMIT,
        location_params={"type": "test-type"},
        body={"hello": "world"},
    )
    client.close()

    records = _read_records(client.replay_log_path)
    assert records[-1]["success"] is False
    assert records[-1]["error"] == "HTTP 500"


def test_argus_client_post_records_2xx_with_error_status_as_failure(requests_mock, tmp_path):
    # The Argus backend returns logical errors as HTTP 200 with
    # ``{"status": "error", "response": {...}}`` (argus/backend/error_handlers.py).
    requests_mock.post(
        "https://test.example.com/api/v1/client/testrun/test-type/submit",
        json={"status": "error", "response": {"exception": "boom"}},
        status_code=200,
    )
    client = ArgusClient(
        auth_token="t",
        base_url="https://test.example.com",
        log_dir=tmp_path,
    )
    client.post(
        endpoint=ArgusClient.Routes.SUBMIT,
        location_params={"type": "test-type"},
        body={},
    )
    client.close()

    records = _read_records(client.replay_log_path)
    assert records[-1]["success"] is False
    assert "status='error'" in records[-1]["error"]


def test_argus_client_post_records_non_json_response_as_failure(requests_mock, tmp_path):
    # Auth proxies (e.g. Cloudflare Access) return plain HTML for
    # unauthenticated requests rather than the JSON envelope.
    requests_mock.post(
        "https://test.example.com/api/v1/client/testrun/test-type/submit",
        text="<html><body>Forbidden</body></html>",
        status_code=200,
        headers={"Content-Type": "text/html"},
    )
    client = ArgusClient(
        auth_token="t",
        base_url="https://test.example.com",
        log_dir=tmp_path,
    )
    client.post(
        endpoint=ArgusClient.Routes.SUBMIT,
        location_params={"type": "test-type"},
        body={},
    )
    client.close()

    records = _read_records(client.replay_log_path)
    assert records[-1]["success"] is False
    assert "non-JSON" in records[-1]["error"]


def test_argus_client_post_records_401_unauthenticated_as_failure(requests_mock, tmp_path):
    requests_mock.post(
        "https://test.example.com/api/v1/client/testrun/test-type/submit",
        text="Unauthorized",
        status_code=401,
    )
    client = ArgusClient(
        auth_token="t",
        base_url="https://test.example.com",
        log_dir=tmp_path,
    )
    client.post(
        endpoint=ArgusClient.Routes.SUBMIT,
        location_params={"type": "test-type"},
        body={},
    )
    client.close()

    records = _read_records(client.replay_log_path)
    assert records[-1]["success"] is False
    assert records[-1]["error"] == "HTTP 401"


def test_argus_client_post_records_exception_on_connection_failure(requests_mock, tmp_path):
    import requests as _requests
    requests_mock.post(
        "https://test.example.com/api/v1/client/testrun/test-type/submit",
        exc=_requests.ConnectionError("connection refused"),
    )
    client = ArgusClient(
        auth_token="t",
        base_url="https://test.example.com",
        log_dir=tmp_path,
    )
    with pytest.raises(Exception):
        client.post(
            endpoint=ArgusClient.Routes.SUBMIT,
            location_params={"type": "test-type"},
            body={},
        )
    client.close()

    records = _read_records(client.replay_log_path)
    assert len(records) == 2
    assert records[-1]["success"] is False
    assert "ConnectionError" in records[-1]["error"]


def test_argus_client_replay_log_only_mode_skips_http_but_records(tmp_path):
    # replay-log-only skips the HTTP call but still records the request so a
    # future replay (Phase 5) can re-send it once Argus is reachable.
    client = ArgusClient(
        auth_token="t",
        base_url="https://unreachable.invalid",
        log_dir=tmp_path,
        replay_log_only=True,
    )
    response = client.post(
        endpoint=ArgusClient.Routes.SUBMIT,
        location_params={"type": "test-type"},
        body={"k": "v"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "response": {}}
    client.close()

    records = _read_records(client.replay_log_path)
    assert len(records) == 2
    for r in records:
        assert r["endpoint"] == ArgusClient.Routes.SUBMIT
        assert r["location_params"] == {"type": "test-type"}
        assert r["body"] == {"k": "v"}
    # No HTTP call was made, so it has not succeeded -- replay must re-send it.
    assert records[-1]["success"] is False


def test_argus_client_replay_log_only_get_returns_stub(tmp_path):
    # In replay-log-only mode GET acts as a mock instead of raising, so
    # callers (e.g. SCT tests that previously used ``MagicMock``) do not
    # have to special-case it.
    client = ArgusClient(
        auth_token="t",
        base_url="https://unreachable.invalid",
        log_dir=tmp_path,
        replay_log_only=True,
    )
    response = client.get(endpoint=ArgusClient.Routes.GET, location_params={"type": "t", "id": "1"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "response": {}}
    client.close()


def test_argus_client_replay_log_path_includes_run_id_when_set(tmp_path):
    from argus.client.sct.client import ArgusSCTClient
    run_id = uuid4()
    client = ArgusSCTClient(
        run_id=run_id,
        auth_token="t",
        base_url="https://test.example.com",
        log_dir=tmp_path,
    )
    assert str(run_id) in client.replay_log_path.name
    assert "scylla-cluster-tests" not in client.replay_log_path.name  # test_type isn't in filename
    client.close()
