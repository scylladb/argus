"""Unit tests for :mod:`argus.backend.service.replay_service`.

These tests do **not** require a live ScyllaDB. They exercise the archive
parsing, ordering, normalisation, skip-list and create_missing_tests
pre-step. Dispatch itself is verified by mocking the Flask app's
``test_client`` -- we record the calls and return canned responses.
"""
from __future__ import annotations

import gzip
import io
import json
import tarfile
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import zstandard as zstd

from argus.backend.service.replay_service import (
    CLIENT_ROUTE_PREFIX,
    FINALIZE_ENDPOINT,
    ReplayService,
    ReplayServiceError,
    SKIP_ENDPOINTS,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_archive(files: dict[str, list[dict]]) -> bytes:
    """Build an in-memory ``tar.zst`` mirroring the on-disk layout."""
    return zstd.ZstdCompressor().compress(_make_tar(files))


def _make_tar(files: dict[str, list[dict]]) -> bytes:
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        for name, records in files.items():
            payload = "\n".join(json.dumps(r) for r in records).encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return tar_buf.getvalue()


def _make_targz(files: dict[str, list[dict]]) -> bytes:
    return gzip.compress(_make_tar(files))


def _make_zip(files: dict[str, list[dict]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, records in files.items():
            payload = "\n".join(json.dumps(r) for r in records).encode("utf-8")
            zf.writestr(name, payload)
    return buf.getvalue()


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
    backfill_logs: bool = False,
    s3_client=None,
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
        backfill_logs=backfill_logs,
        s3_client=s3_client,
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


@pytest.mark.parametrize("packer", [_make_tar, _make_targz, _make_zip, _make_archive])
def test_ingest_accepts_each_supported_format(packer):
    archive = packer({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "generic"}, body={"run_id": "x"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200, b'{"status":"ok"}')
    summary = _make_service(client).ingest(archive)
    assert summary.total == 1
    assert summary.succeeded == 1
    assert client.open.call_count == 1


def test_ingest_rejects_unknown_format():
    # Long enough to clear all magic-byte checks but recognised by none.
    with pytest.raises(ReplayServiceError, match="unrecognised format"):
        _make_service().ingest(b"hello world" * 60)


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


def test_finalize_is_dispatched_and_runs_in_terminal_group():
    # ``finalize`` is the ONLY call that back-fills a generic (dtest/pytest)
    # run's terminal status/scylla_version/end_time. Regression guard: it must
    # be dispatched (not skipped) and ordered after every middle record, even
    # when its ts is older than a middle record's.
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec(FINALIZE_ENDPOINT, ts=5,
                 location_params={"type": "generic", "id": "X"},
                 body={"status": "passed", "scylla_version": "6.2.0"}),
            _rec("/testrun/$type/$id/submit_results", ts=10,
                 location_params={"type": "generic", "id": "X"},
                 body={"run_id": "X"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    urls = [c.args[0] for c in client.open.call_args_list]
    assert urls == [
        f"{CLIENT_ROUTE_PREFIX}/testrun/generic/X/submit_results",
        f"{CLIENT_ROUTE_PREFIX}/testrun/generic/X/finalize",
    ]
    # The terminal status/version payload is forwarded intact, and the run's
    # original finish time is injected from the record ts, which is in
    # milliseconds (5ms -> 0.005s).
    final_json = client.open.call_args.kwargs["json"]
    assert final_json["status"] == "passed"
    assert final_json["scylla_version"] == "6.2.0"
    assert final_json["end_time"] == 5 / 1000


def test_finalize_end_time_is_injected_from_ts_when_absent():
    # ReplayRecord.ts is milliseconds (== _now_ns() // 1_000_000), so a ts of
    # 1_700_000_000_000ms must inject end_time == 1_700_000_000.0s.
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec(FINALIZE_ENDPOINT, ts=1_700_000_000_000,
                 location_params={"type": "generic", "id": "X"},
                 body={"status": "passed"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    assert client.open.call_args.kwargs["json"]["end_time"] == 1_700_000_000.0


def test_finalize_preserves_explicit_end_time_in_body():
    # A finalize record that already carries end_time is left untouched.
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec(FINALIZE_ENDPOINT, ts=5,
                 location_params={"type": "generic", "id": "X"},
                 body={"status": "passed", "end_time": 1234.5}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    assert client.open.call_args.kwargs["json"]["end_time"] == 1234.5


def test_finalize_end_time_falls_back_to_last_seen_ts_when_own_ts_absent():
    # The finalize record itself has no ts (e.g. reconstructed rather than
    # originally recorded) -- fall back to the highest ts seen anywhere in
    # the replay log for this run, not the replay moment, since recovering
    # from an outage can take days and the run itself may be days-long.
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/$id/submit_results", ts=10,
                 location_params={"type": "generic", "id": "X"},
                 body={"run_id": "X"}),
            _rec("/testrun/$type/$id/heartbeat", ts=1_700_000_000_000,
                 location_params={"type": "generic", "id": "X"}, body={}),
            _rec(FINALIZE_ENDPOINT, ts=0,
                 location_params={"type": "generic", "id": "X"},
                 body={"status": "passed"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    finalize_call = next(
        c for c in client.open.call_args_list
        if c.args[0].endswith("/finalize"))
    assert finalize_call.kwargs["json"]["end_time"] == 1_700_000_000.0


def test_finalize_end_time_untouched_when_no_ts_anywhere_for_run():
    # No record for the run carries a ts at all -- end_time is left unset,
    # same as before this fallback existed, rather than injecting a bogus 0.
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec(FINALIZE_ENDPOINT, ts=0,
                 location_params={"type": "generic", "id": "X"},
                 body={"status": "passed"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    assert "end_time" not in client.open.call_args.kwargs["json"]


def test_finalize_runs_after_terminal_set_status():
    # When both are present (the SCT flow emits set_status *and* finalize),
    # finalize still lands last so end_time is written after the status flip.
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec(FINALIZE_ENDPOINT, ts=5,
                 location_params={"type": "scylla-cluster-tests", "id": "X"},
                 body={}),
            _rec("/testrun/$type/$id/set_status", ts=10,
                 location_params={"type": "scylla-cluster-tests", "id": "X"},
                 body={"new_status": "passed"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    _make_service(client).ingest(archive)
    urls = [c.args[0] for c in client.open.call_args_list]
    assert urls == [
        f"{CLIENT_ROUTE_PREFIX}/testrun/scylla-cluster-tests/X/set_status",
        f"{CLIENT_ROUTE_PREFIX}/testrun/scylla-cluster-tests/X/finalize",
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

def test_finalize_is_not_in_skip_list():
    # finalize has no side effect outside Argus (it only writes the run row)
    # and is the sole terminal-state source for non-SCT plugins, so it must be
    # replayed, not skipped.
    assert FINALIZE_ENDPOINT not in SKIP_ENDPOINTS


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
    # Patch the diagnosis to None (i.e. the test entity already exists) so
    # the dispatch path runs unchanged -- this test is about the auto-create
    # branch staying off, not about the pre-check.
    with patch.object(ReplayService, "_diagnose_missing_hierarchy", return_value=None), \
         patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure:
        summary = svc.ingest(archive)
    ensure.assert_not_called()
    assert client.open.call_count == 1
    assert summary.succeeded == 1


def test_missing_hierarchy_pre_check_fails_record_with_diagnosis():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "scylla-cluster-tests"},
                 body={"run_id": "abc",
                       "job_name": "scylla-staging/dusan/longevity-test"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    svc = _make_service(client, create_missing_tests=False)
    diagnosis = (
        "test entity missing for build_id='scylla-staging/dusan/longevity-test': "
        "would create release='scylla-staging', group='dusan', test='longevity-test'; "
        "currently missing: release, group, test. ..."
    )
    with patch.object(ReplayService, "_diagnose_missing_hierarchy", return_value=diagnosis):
        summary = svc.ingest(archive)
    assert client.open.call_count == 0  # dispatch was blocked
    assert summary.failed == 1
    assert summary.succeeded == 0
    assert len(summary.errors) == 1
    assert summary.errors[0]["endpoint"] == "/testrun/$type/submit"
    assert summary.errors[0]["error"] == diagnosis


def test_missing_hierarchy_pre_check_runs_in_dry_run():
    """dry_run still surfaces the diagnosis so users can preview what would
    fail without uploading -- the whole point of dry_run."""
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "generic"},
                 body={"run_id": "x", "job_name": "some/job"}),
        ],
    })
    client = MagicMock()
    svc = _make_service(client, create_missing_tests=False)
    with patch.object(ReplayService, "_diagnose_missing_hierarchy", return_value="diag"):
        summary = svc.ingest(archive, dry_run=True)
    assert client.open.call_count == 0
    assert summary.failed == 1
    assert summary.errors[0]["error"] == "diag"


def test_pre_check_exception_does_not_block_dispatch():
    """If the pre-check itself raises (e.g. transient DB error), the dispatch
    still runs -- pre-check failures must never harden into outages."""
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "generic"},
                 body={"run_id": "x", "job_name": "some/job"}),
        ],
    })
    client = MagicMock()
    client.open.return_value = _Response(200)
    svc = _make_service(client, create_missing_tests=False)
    with patch.object(
        ReplayService, "_diagnose_missing_hierarchy",
        side_effect=RuntimeError("db down"),
    ):
        summary = svc.ingest(archive)
    assert client.open.call_count == 1
    assert summary.succeeded == 1


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


# ---------------------------------------------------------------------------
# _diagnose_missing_hierarchy (direct unit tests for the diagnosis logic)
# ---------------------------------------------------------------------------

def _patch_hierarchy_models(*, test_exists: bool,
                            release_exists: bool = True,
                            group_exists: bool = True):
    """Patch ArgusRelease/ArgusGroup/ArgusTest at their replay_service import
    sites to simulate which entities exist in the database."""
    import argus.backend.models.web as web

    class _DNE(Exception):
        pass

    test_mock = MagicMock()
    test_mock.DoesNotExist = web.ArgusTest.DoesNotExist
    if test_exists:
        test_mock.get.return_value = MagicMock()
    else:
        test_mock.get.side_effect = web.ArgusTest.DoesNotExist

    release_mock = MagicMock()
    release_mock.DoesNotExist = web.ArgusRelease.DoesNotExist
    if release_exists:
        rel = MagicMock(id="rel-id")
        release_mock.get.return_value = rel
    else:
        release_mock.get.side_effect = web.ArgusRelease.DoesNotExist

    group_mock = MagicMock()
    if release_exists and group_exists:
        g = MagicMock(build_system_id="scylla-staging/dusan")
        group_mock.filter.return_value.all.return_value = [g]
    else:
        group_mock.filter.return_value.all.return_value = []

    return patch.multiple(
        "argus.backend.models.web",
        ArgusRelease=release_mock,
        ArgusGroup=group_mock,
        ArgusTest=test_mock,
    ), _DNE


def _submit_record(build_id: str) -> dict:
    return _rec("/testrun/$type/submit", ts=1,
                location_params={"type": "scylla-cluster-tests"},
                body={"run_id": "abc", "job_name": build_id})


def test_diagnose_returns_none_when_test_exists():
    patcher, _ = _patch_hierarchy_models(test_exists=True)
    with patcher:
        result = ReplayService._diagnose_missing_hierarchy(
            _submit_record("scylla-staging/dusan/longevity-test")
        )
    assert result is None


def test_diagnose_returns_none_when_no_build_id():
    # No DB lookup should be attempted; safe to call without patching models.
    assert ReplayService._diagnose_missing_hierarchy(
        _rec("/testrun/$type/submit", ts=1,
             location_params={"type": "generic"},
             body={"run_id": "abc"})
    ) is None


def test_diagnose_reports_all_three_missing_when_release_absent():
    patcher, _ = _patch_hierarchy_models(test_exists=False, release_exists=False)
    with patcher:
        result = ReplayService._diagnose_missing_hierarchy(
            _submit_record("scylla-staging/dusan/longevity-test")
        )
    assert result is not None
    assert "release='scylla-staging'" in result
    assert "group='dusan'" in result
    assert "test='longevity-test'" in result
    assert "currently missing: release, group, test" in result
    assert "--create-missing-tests" in result


def test_diagnose_reports_group_and_test_missing_when_only_release_exists():
    patcher, _ = _patch_hierarchy_models(
        test_exists=False, release_exists=True, group_exists=False,
    )
    with patcher:
        result = ReplayService._diagnose_missing_hierarchy(
            _submit_record("scylla-staging/dusan/longevity-test")
        )
    assert result is not None
    assert "currently missing: group, test" in result


def test_diagnose_reports_only_test_missing_when_release_and_group_exist():
    patcher, _ = _patch_hierarchy_models(
        test_exists=False, release_exists=True, group_exists=True,
    )
    with patcher:
        result = ReplayService._diagnose_missing_hierarchy(
            _submit_record("scylla-staging/dusan/longevity-test")
        )
    assert result is not None
    assert "currently missing: test" in result
    # Make sure we didn't accidentally mark release or group as missing too.
    assert "release," not in result.split("currently missing:")[1]
    assert "group," not in result.split("currently missing:")[1]


def test_diagnose_parses_two_segment_build_id():
    """``release/test`` form: group becomes ``<release>-root`` per
    parse_build_id; group's build_system_id is the release name."""
    patcher, _ = _patch_hierarchy_models(test_exists=False, release_exists=False)
    with patcher:
        result = ReplayService._diagnose_missing_hierarchy(
            _submit_record("scylla-master/perf")
        )
    assert result is not None
    assert "release='scylla-master'" in result
    assert "group='scylla-master-root'" in result
    assert "test='perf'" in result


# ---------------------------------------------------------------------------
# S3 log back-fill (backfill_logs=True)
# ---------------------------------------------------------------------------

_RUN_ID = "15bb6cad-1d24-4e81-800e-9c45d6ea7d06"
_BUCKET = "cloudius-jenkins-test"


def _s3_url(key: str) -> str:
    return f"https://{_BUCKET}.s3.amazonaws.com/{key}"


def _mock_s3(keys: list[str]):
    """A boto3-S3 stand-in whose ``list_objects_v2`` returns ``keys``."""
    s3 = MagicMock()
    s3.list_objects_v2.return_value = {
        "Contents": [{"Key": k} for k in keys],
        "IsTruncated": False,
    }
    return s3


def _logs_archive(recorded_keys: list[str]) -> bytes:
    """Archive with a single ``logs/submit`` recording links for ``recorded_keys``."""
    return _make_archive({"argus_replay_log_run.jsonl": [
        _rec("/testrun/$type/$id/logs/submit", ts=1,
             location_params={"type": "scylla-cluster-tests", "id": _RUN_ID},
             body={"schema_version": "v8", "logs": [
                 {"log_name": k.rsplit("/", 1)[-1], "log_link": _s3_url(k)}
                 for k in recorded_keys
             ]}),
    ]})


def test_backfill_submits_only_missing_s3_objects():
    recorded = f"{_RUN_ID}/20260526_115014/db-node-0-1-15bb6cad.tar.zst"
    loader = f"{_RUN_ID}/20260526_115014/loader-set-15bb6cad.tar.zst"
    runner = f"{_RUN_ID}/20260526_115014/sct-runner-events-15bb6cad.tar.zst"
    s3 = _mock_s3([recorded, loader, runner])

    client = MagicMock()
    client.open.return_value = _Response(200, b'{"status":"ok"}')
    service = _make_service(client, backfill_logs=True, s3_client=s3)
    summary = service.ingest(_logs_archive([recorded]))

    # Listed the run's prefix once.
    s3.list_objects_v2.assert_called_once()
    assert s3.list_objects_v2.call_args.kwargs["Prefix"] == f"{_RUN_ID}/"

    # Two dispatches: the recorded logs/submit + one back-fill logs/submit.
    bodies = [c.kwargs["json"] for c in client.open.call_args_list]
    backfill_bodies = [b for b in bodies if b and any(
        "loader-set" in l["log_name"] or "sct-runner" in l["log_name"] for l in b.get("logs", []))]
    assert len(backfill_bodies) == 1
    submitted = {l["log_link"] for l in backfill_bodies[0]["logs"]}
    # Only the two *missing* archives, never the already-recorded db-node link.
    assert submitted == {_s3_url(loader), _s3_url(runner)}
    assert _s3_url(recorded) not in submitted
    assert summary.backfilled_logs == 2


def test_backfill_can_be_disabled():
    # The ingest endpoint enables backfill by default; passing backfill_logs=False
    # (?backfill_logs=false) must suppress the S3 listing entirely.
    recorded = f"{_RUN_ID}/20260526_115014/db-node-0-1-15bb6cad.tar.zst"
    loader = f"{_RUN_ID}/20260526_115014/loader-set-15bb6cad.tar.zst"
    s3 = _mock_s3([recorded, loader])

    client = MagicMock()
    client.open.return_value = _Response(200, b'{"status":"ok"}')
    service = _make_service(client, backfill_logs=False, s3_client=s3)
    summary = service.ingest(_logs_archive([recorded]))

    s3.list_objects_v2.assert_not_called()
    assert summary.backfilled_logs == 0


def test_backfill_noop_when_all_logs_already_present():
    recorded = f"{_RUN_ID}/20260526_115014/db-node-0-1-15bb6cad.tar.zst"
    s3 = _mock_s3([recorded])  # S3 has nothing new

    client = MagicMock()
    client.open.return_value = _Response(200, b'{"status":"ok"}')
    service = _make_service(client, backfill_logs=True, s3_client=s3)
    summary = service.ingest(_logs_archive([recorded]))

    assert summary.backfilled_logs == 0
    # Only the single recorded logs/submit was dispatched.
    assert client.open.call_count == 1


def test_backfill_skipped_on_dry_run():
    recorded = f"{_RUN_ID}/20260526_115014/db-node-0-1-15bb6cad.tar.zst"
    loader = f"{_RUN_ID}/20260526_115014/loader-set-15bb6cad.tar.zst"
    s3 = _mock_s3([recorded, loader])

    service = _make_service(backfill_logs=True, s3_client=s3)
    summary = service.ingest(_logs_archive([recorded]), dry_run=True)

    s3.list_objects_v2.assert_not_called()
    assert summary.backfilled_logs == 0


def test_backfill_falls_back_to_sct_default_bucket_when_no_bucket_derivable():
    # Only a non-S3 link recorded -> no bucket to learn from, and no
    # REPLAY_LOG_BACKFILL_BUCKET config (no app context in tests) -- falls
    # back to SCT's own default bucket rather than silently skipping.
    loader = f"{_RUN_ID}/x/loader-set.tar.zst"
    archive = _make_archive({"argus_replay_log_run.jsonl": [
        _rec("/testrun/$type/$id/logs/submit", ts=1,
             location_params={"type": "scylla-cluster-tests", "id": _RUN_ID},
             body={"schema_version": "v8", "logs": [
                 {"log_name": "local", "log_link": "http://example.com/local.tar.zst"}]}),
    ]})
    s3 = _mock_s3([loader])

    service = _make_service(backfill_logs=True, s3_client=s3)
    summary = service.ingest(archive)

    s3.list_objects_v2.assert_called_once_with(Bucket=_BUCKET, Prefix=f"{_RUN_ID}/")
    assert summary.backfilled_logs == 1


def test_log_name_from_key_strips_archive_suffix():
    assert ReplayService._log_name_from_key(
        f"{_RUN_ID}/ts/loader-set-15bb6cad.tar.zst") == "loader-set-15bb6cad"
    assert ReplayService._log_name_from_key(
        f"{_RUN_ID}/ts/history.jsonl.tar.gz") == "history.jsonl"
    assert ReplayService._log_name_from_key(f"{_RUN_ID}/ts/plain.log") == "plain.log"
