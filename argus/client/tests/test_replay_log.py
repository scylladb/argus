"""Tests for the JSONL Argus replay log."""
import json
import threading
from uuid import uuid4

import pytest

from argus.client.base import ArgusClient
from argus.client.replay_log import ReplayLog


def _read_records(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_replay_log_writes_single_jsonl_record_per_call(tmp_path):
    log = ReplayLog(log_dir=tmp_path, run_id="run-1", test_type="generic")
    with log.record("POST", "/foo/$id", {"id": "abc"}, None, {"k": "v"}) as rec:
        rec.success = True
    log.close()

    records = _read_records(log.path)
    assert len(records) == 1
    r = records[0]
    assert r["method"] == "POST"
    assert r["endpoint"] == "/foo/$id"
    assert r["location_params"] == {"id": "abc"}
    assert r["params"] is None
    assert r["body"] == {"k": "v"}
    assert r["test_type"] == "generic"
    assert r["success"] is True
    assert "error" not in r
    assert isinstance(r["ts"], int)


def test_replay_log_round_trips_non_none_params(tmp_path):
    log = ReplayLog(log_dir=tmp_path, run_id="r", test_type="t")
    location_params = {"id": "abc", "kind": "sct"}
    query_params = {"limit": 50, "active": True}
    body = {"nested": {"a": [1, 2, 3]}, "name": "x"}
    with log.record("POST", "/foo/$id", location_params, query_params, body) as rec:
        rec.success = True
    log.close()

    [r] = _read_records(log.path)
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
    assert len(records) == 1
    assert records[0]["success"] is False
    assert records[0]["error"].startswith("RuntimeError: boom")


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
    assert _read_records(path)[0]["success"] is True


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
    assert len(records) == n_threads * per_thread
    # No partial lines / no JSON corruption.
    seen = {(r["body"]["tid"], r["body"]["i"]) for r in records}
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
    assert len(records) == 1
    assert records[0]["endpoint"] == ArgusClient.Routes.SUBMIT
    assert records[0]["location_params"] == {"type": "test-type"}
    assert records[0]["body"] == {"hello": "world"}
    assert records[0]["success"] is True


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
    assert len(records) == 1
    assert records[0]["success"] is False
    assert records[0]["error"] == "HTTP 500"


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
    assert records[0]["success"] is False
    assert "status='error'" in records[0]["error"]


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
    assert records[0]["success"] is False
    assert "non-JSON" in records[0]["error"]


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
    assert records[0]["success"] is False
    assert records[0]["error"] == "HTTP 401"


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
    assert len(records) == 1
    assert records[0]["success"] is False
    assert "ConnectionError" in records[0]["error"]


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
    assert len(records) == 1
    assert records[0]["endpoint"] == ArgusClient.Routes.SUBMIT
    assert records[0]["location_params"] == {"type": "test-type"}
    assert records[0]["body"] == {"k": "v"}
    # No HTTP call was made, so it has not succeeded -- replay must re-send it.
    assert records[0]["success"] is False


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
