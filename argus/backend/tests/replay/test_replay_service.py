"""Unit tests for :mod:`argus.backend.service.replay_service`.

These tests do **not** require a live ScyllaDB. They exercise the archive
parsing, ordering, normalisation, skip-list and create_missing_tests
pre-step. Dispatch itself is verified by mocking the Flask app's
``test_client`` -- we record the calls and return canned responses.
"""
from __future__ import annotations

import io
import json
import tarfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import zstandard as zstd

from argus.backend.service.replay_service import (
    CLIENT_ROUTE_PREFIX,
    ReplayService,
    ReplayServiceError,
    SKIP_ENDPOINTS,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_archive(files: dict[str, list[dict]]) -> bytes:
    """Build an in-memory ``tar.zst`` mirroring the on-disk layout."""
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        for name, records in files.items():
            payload = "\n".join(json.dumps(r) for r in records).encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return zstd.ZstdCompressor().compress(tar_buf.getvalue())


def _rec(endpoint: str, *, ts: int, location_params: dict | None = None,
         body: dict | None = None, method: str = "POST",
         success: bool = True) -> dict:
    return {
        "ts": ts,
        "method": method,
        "endpoint": endpoint,
        "location_params": location_params,
        "params": None,
        "body": body,
        "test_type": "scylla-cluster-tests",
        "success": success,
    }


class _Response:
    """Minimal stand-in for a Werkzeug response, sufficient for the service."""

    def __init__(self, status_code: int = 200, body: bytes | dict = b"") -> None:
        self.status_code = status_code
        if isinstance(body, dict):
            self._body = json.dumps(body).encode()
            self._json = body
        else:
            self._body = body
            try:
                self._json = json.loads(body.decode())
            except Exception:
                self._json = None

    def get_data(self, *, as_text: bool = False):
        return self._body.decode() if as_text else self._body

    def get_json(self, *, silent: bool = False):
        return self._json


def _make_app(client) -> SimpleNamespace:
    """Stand-in for a Flask app whose ``test_client()`` returns ``client``."""
    return SimpleNamespace(test_client=lambda: client)


def _make_service(
    client=None,
    *,
    create_missing_tests: bool = False,
    auth_header: str | None = None,
) -> ReplayService:
    """Service wired to a recording mock client (default: always-200)."""
    if client is None:
        client = MagicMock()
        client.open.return_value = _Response(200, b'{"status":"ok"}')
    app = _make_app(client)
    return ReplayService(
        app=app,
        auth_header=auth_header,
        create_missing_tests=create_missing_tests,
    )


# ---------------------------------------------------------------------------
# archive parsing
# ---------------------------------------------------------------------------

def test_ingest_empty_archive_yields_empty_summary():
    summary = _make_service().ingest(_make_archive({}))
    assert summary.total == 0
    assert summary.processed == 0


def test_ingest_rejects_corrupt_archive():
    with pytest.raises(ReplayServiceError):
        _make_service().ingest(b"not a tar.zst archive")


def test_ingest_skips_non_jsonl_members():
    archive_bytes = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "generic"},
                 body={"run_id": "x"}),
        ],
    })
    decompressor = zstd.ZstdDecompressor()
    with decompressor.stream_reader(io.BytesIO(archive_bytes)) as stream:
        decompressed = stream.read()
    extra = io.BytesIO()
    with tarfile.open(fileobj=extra, mode="w") as tar:
        with tarfile.open(fileobj=io.BytesIO(decompressed), mode="r") as src:
            for m in src:
                fobj = src.extractfile(m)
                tar.addfile(m, fobj)
        readme = b"hello"
        info = tarfile.TarInfo(name="README.txt")
        info.size = len(readme)
        tar.addfile(info, io.BytesIO(readme))
    archive = zstd.ZstdCompressor().compress(extra.getvalue())

    client = MagicMock()
    client.open.return_value = _Response(200, b'{"status":"ok"}')
    summary = _make_service(client).ingest(archive)
    assert summary.total == 1
    assert summary.succeeded == 1
    assert client.open.call_count == 1


def test_ingest_skips_malformed_jsonl_lines():
    tar_buf = io.BytesIO()
    payload = b'{"ts":1,"endpoint":"/testrun/$type/submit","location_params":{"type":"generic"},"body":{}}\n'
    payload += b"this is not json\n"
    payload += b'{"ts":2,"endpoint":"/testrun/$type/submit","location_params":{"type":"generic"},"body":{}}\n'
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        info = tarfile.TarInfo(name="argus_replay_log_r_1.jsonl")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    archive = zstd.ZstdCompressor().compress(tar_buf.getvalue())

    summary = _make_service().ingest(archive)
    assert summary.total == 2  # malformed line dropped
    assert summary.succeeded == 2


# ---------------------------------------------------------------------------
# ordering
# ---------------------------------------------------------------------------

def test_records_sorted_by_ts():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=30,
                 location_params={"id": "X"}, body={"data": {"k": 3}}),
            _rec("/sct/$id/event/submit", ts=10,
                 location_params={"id": "X"}, body={"data": {"k": 1}}),
            _rec("/sct/$id/event/submit", ts=20,
                 location_params={"id": "X"}, body={"data": {"k": 2}}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    seen = [c.kwargs["json"]["data"]["k"] for c in client.open.call_args_list]
    assert seen == [1, 2, 3]


def test_submit_run_is_ordered_first():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=5,
                 location_params={"id": "X"}, body={"data": {}}),
            _rec("/testrun/$type/submit", ts=100,  # newer ts but must run first
                 location_params={"type": "scylla-cluster-tests"},
                 body={"run_id": "X"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    first_call_url = client.open.call_args_list[0].args[0]
    assert first_call_url == f"{CLIENT_ROUTE_PREFIX}/testrun/scylla-cluster-tests/submit"


def test_terminal_set_status_runs_last():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/$id/set_status", ts=5,
                 location_params={"type": "t", "id": "X"},
                 body={"new_status": "passed"}),
            _rec("/sct/$id/event/submit", ts=10,
                 location_params={"id": "X"}, body={"data": {}}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    urls = [c.args[0] for c in client.open.call_args_list]
    assert urls == [
        f"{CLIENT_ROUTE_PREFIX}/sct/X/event/submit",
        f"{CLIENT_ROUTE_PREFIX}/testrun/t/X/set_status",
    ]


def test_non_terminal_set_status_keeps_natural_order():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/$id/set_status", ts=5,
                 location_params={"type": "t", "id": "X"},
                 body={"new_status": "running"}),
            _rec("/sct/$id/event/submit", ts=10,
                 location_params={"id": "X"}, body={"data": {}}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    urls = [c.args[0] for c in client.open.call_args_list]
    assert urls == [
        f"{CLIENT_ROUTE_PREFIX}/testrun/t/X/set_status",
        f"{CLIENT_ROUTE_PREFIX}/sct/X/event/submit",
    ]


def test_heartbeats_collapse_to_last():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/$id/heartbeat", ts=5,
                 location_params={"type": "t", "id": "X"}, body={"hb": 1}),
            _rec("/testrun/$type/$id/heartbeat", ts=20,
                 location_params={"type": "t", "id": "X"}, body={"hb": 2}),
            _rec("/testrun/$type/$id/heartbeat", ts=15,
                 location_params={"type": "t", "id": "X"}, body={"hb": 3}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    assert client.open.call_count == 1
    # The "last" heartbeat is the one with the highest ts (20).
    assert client.open.call_args.kwargs["json"] == {"hb": 2}


# ---------------------------------------------------------------------------
# URL reconstruction
# ---------------------------------------------------------------------------

def test_url_substitutes_location_params():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/resource/$name/terminate", ts=1,
                 location_params={"id": "RUN", "name": "node-1"},
                 body={"reason": "manual"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    assert client.open.call_args.args[0] == (
        f"{CLIENT_ROUTE_PREFIX}/sct/RUN/resource/node-1/terminate"
    )


def test_double_slash_endpoint_is_normalised():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id//stress_cmd/submit", ts=1,
                 location_params={"id": "RUN"},
                 body={"cmd": "stress"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    assert client.open.call_args.args[0] == (
        f"{CLIENT_ROUTE_PREFIX}/sct/RUN/stress_cmd/submit"
    )


# ---------------------------------------------------------------------------
# auth header propagation
# ---------------------------------------------------------------------------

def test_auth_header_is_forwarded():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=1,
                 location_params={"id": "X"}, body={"data": {}}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    svc = _make_service(client, auth_header="token abc")
    svc.ingest(archive)
    assert client.open.call_args.kwargs["headers"] == {"Authorization": "token abc"}


# ---------------------------------------------------------------------------
# skip list
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("endpoint", sorted(SKIP_ENDPOINTS))
def test_skip_endpoints_are_not_dispatched(endpoint: str):
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec(endpoint, ts=1, location_params={"id": "X", "type": "t"},
                 body={}),
        ],
    })
    client = MagicMock()
    summary = _make_service(client).ingest(archive)
    assert summary.skipped_no_replay == 1
    assert client.open.call_count == 0


# ---------------------------------------------------------------------------
# response handling
# ---------------------------------------------------------------------------

def test_non_2xx_response_is_recorded_as_failure():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=1,
                 location_params={"id": "X"}, body={"data": {}}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(500, b"boom")
    summary = _make_service(client).ingest(archive)
    assert summary.failed == 1
    assert summary.succeeded == 0
    assert "HTTP 500" in summary.errors[0]["error"]


def test_2xx_envelope_error_is_recorded_as_failure():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=1,
                 location_params={"id": "X"}, body={"data": {}}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200, {
        "status": "error",
        "response": {"exception": "ValueError", "arguments": ["bad input"]},
    })
    summary = _make_service(client).ingest(archive)
    assert summary.failed == 1
    assert "ValueError" in summary.errors[0]["error"]


def test_client_open_exception_is_isolated():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=1, location_params={"id": "X"}, body={}),
            _rec("/sct/$id/event/submit", ts=2, location_params={"id": "Y"}, body={}),
        ],
    })
    client = MagicMock()
    client.open.side_effect = [RuntimeError("kaboom"), _Response(200, b'{"status":"ok"}')]
    summary = _make_service(client).ingest(archive)
    assert summary.failed == 1
    assert summary.succeeded == 1
    assert "RuntimeError" in summary.errors[0]["error"]


# ---------------------------------------------------------------------------
# dry_run
# ---------------------------------------------------------------------------

def test_dry_run_does_not_dispatch():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=1, location_params={"id": "X"}, body={}),
            _rec("/testrun/$type/submit", ts=0,
                 location_params={"type": "generic"}, body={"run_id": "X"}),
        ],
    })
    client = MagicMock()
    summary = _make_service(client).ingest(archive, dry_run=True)
    assert summary.succeeded == 2
    assert client.open.call_count == 0


# ---------------------------------------------------------------------------
# create_missing_tests pre-step
# ---------------------------------------------------------------------------

def test_create_missing_tests_invokes_hierarchy_on_submit_run():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "scylla-cluster-tests"},
                 body={"run_id": "550e8400-e29b-41d4-a716-446655440000",
                       "job_name": "scylla-staging/dusan/longevity-test",
                       "job_url": "https://jenkins.example/job/x"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200, b'{"status":"ok"}')
    svc = _make_service(client, create_missing_tests=True)
    with patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure, \
         patch("argus.backend.service.client_service.ClientService"):
        summary = svc.ingest(archive)
    assert summary.succeeded == 1
    ensure.assert_called_once()
    kwargs = ensure.call_args.kwargs
    assert kwargs["build_id"] == "scylla-staging/dusan/longevity-test"
    assert kwargs["plugin_name"] == "scylla-cluster-tests"


def test_create_missing_tests_disabled_by_default():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "generic"},
                 body={"run_id": "x", "build_id": "scylla-master/perf"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    svc = _make_service(client, create_missing_tests=False)
    with patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure:
        svc.ingest(archive)
    ensure.assert_not_called()


def test_create_missing_tests_failure_does_not_abort_dispatch():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "scylla-cluster-tests"},
                 body={"run_id": "x", "job_name": "scylla-staging/dusan/lt"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200, b'{"status":"ok"}')
    svc = _make_service(client, create_missing_tests=True)
    with patch(
        "argus.backend.service.test_hierarchy.ensure_test_hierarchy",
        side_effect=RuntimeError("db down"),
    ) as ensure:
        summary = svc.ingest(archive)
    ensure.assert_called_once()
    assert client.open.call_count == 1  # dispatch still ran
    assert summary.succeeded == 1


def test_create_missing_tests_skips_when_no_build_id_in_body():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "sirenada"},
                 body={"run_id": "x"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    svc = _make_service(client, create_missing_tests=True)
    with patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure:
        svc.ingest(archive)
    ensure.assert_not_called()
