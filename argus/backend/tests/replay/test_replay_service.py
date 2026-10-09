"""Unit tests for :mod:`argus.backend.service.replay_service`.

These tests do **not** require a live ScyllaDB. They exercise the archive
parsing, ordering, normalisation, skip-list and create_missing_tests
pre-step. Dispatch itself is verified by injecting a mock ``httpx`` client
-- we record the calls and return canned responses.
"""
from __future__ import annotations

import gzip
import io
import json
import tarfile
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
import zstandard as zstd

from coodie.exceptions import DocumentNotFound

from argus.backend.error_handlers import DataValidationError
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
    """Minimal stand-in for an httpx response, sufficient for the service."""

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

    @property
    def text(self) -> str:
        return self._body.decode()

    def json(self):
        if self._json is None:
            raise ValueError("No JSON body")
        return self._json


def _make_service(
    client=None,
    *,
    create_missing_tests: bool = False,
    auth_header: str | None = None,
    backfill_logs: bool = False,
    build_id: str | None = None,
    caller=None,
    as_me: bool | None = None,
    resume_run_id=None,
    local_runs: bool = False,
    s3_client=None,
) -> ReplayService:
    """Service wired to a recording mock client (default: always-200)."""
    if client is None:
        client = AsyncMock()
        client.request.return_value = _Response(200, b'{"status":"ok"}')
    return ReplayService(
        client=client,
        auth_header=auth_header,
        create_missing_tests=create_missing_tests,
        backfill_logs=backfill_logs,
        build_id=build_id,
        caller=caller,
        as_me=as_me,
        resume_run_id=resume_run_id,
        local_runs=local_runs,
        s3_client=s3_client,
    )


# ---------------------------------------------------------------------------
# archive parsing
# ---------------------------------------------------------------------------

async def test_ingest_empty_archive_yields_empty_summary():
    summary = await _make_service().ingest(_make_archive({}))
    assert summary.total == 0
    assert summary.processed == 0


async def test_ingest_rejects_corrupt_archive():
    with pytest.raises(ReplayServiceError):
        await _make_service().ingest(b"not a tar.zst archive")


@pytest.mark.parametrize("packer", [_make_tar, _make_targz, _make_zip, _make_archive])
async def test_ingest_accepts_each_supported_format(packer):
    archive = packer({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "generic"}, body={"run_id": "x"}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200, b'{"status":"ok"}')
    summary = await _make_service(client).ingest(archive)
    assert summary.total == 1
    assert summary.succeeded == 1
    assert client.request.call_count == 1


async def test_ingest_rejects_unknown_format():
    # Long enough to clear all magic-byte checks but recognised by none.
    with pytest.raises(ReplayServiceError, match="unrecognised format"):
        await _make_service().ingest(b"hello world" * 60)


async def test_ingest_skips_non_jsonl_members():
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

    client = AsyncMock()
    client.request.return_value = _Response(200, b'{"status":"ok"}')
    summary = await _make_service(client).ingest(archive)
    assert summary.total == 1
    assert summary.succeeded == 1
    assert client.request.call_count == 1


async def test_ingest_skips_malformed_jsonl_lines():
    tar_buf = io.BytesIO()
    payload = b'{"ts":1,"endpoint":"/testrun/$type/submit","location_params":{"type":"generic"},"body":{}}\n'
    payload += b"this is not json\n"
    payload += b'{"ts":2,"endpoint":"/testrun/$type/submit","location_params":{"type":"generic"},"body":{}}\n'
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        info = tarfile.TarInfo(name="argus_replay_log_r_1.jsonl")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    archive = zstd.ZstdCompressor().compress(tar_buf.getvalue())

    summary = await _make_service().ingest(archive)
    assert summary.total == 2  # malformed line dropped
    assert summary.succeeded == 2


# ---------------------------------------------------------------------------
# ordering
# ---------------------------------------------------------------------------

async def test_records_sorted_by_ts():
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
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    seen = [c.kwargs["json"]["data"]["k"] for c in client.request.call_args_list]
    assert seen == [1, 2, 3]


async def test_submit_run_is_ordered_first():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=5,
                 location_params={"id": "X"}, body={"data": {}}),
            _rec("/testrun/$type/submit", ts=100,  # newer ts but must run first
                 location_params={"type": "scylla-cluster-tests"},
                 body={"run_id": "X"}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    first_call_url = client.request.call_args_list[0].args[1]
    assert first_call_url == f"{CLIENT_ROUTE_PREFIX}/testrun/scylla-cluster-tests/submit"


async def test_terminal_set_status_runs_last():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/$id/set_status", ts=5,
                 location_params={"type": "t", "id": "X"},
                 body={"new_status": "passed"}),
            _rec("/sct/$id/event/submit", ts=10,
                 location_params={"id": "X"}, body={"data": {}}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    urls = [c.args[1] for c in client.request.call_args_list]
    assert urls == [
        f"{CLIENT_ROUTE_PREFIX}/sct/X/event/submit",
        f"{CLIENT_ROUTE_PREFIX}/testrun/t/X/set_status",
    ]


async def test_finalize_is_dispatched_and_runs_in_terminal_group():
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
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    urls = [c.args[1] for c in client.request.call_args_list]
    assert urls == [
        f"{CLIENT_ROUTE_PREFIX}/testrun/generic/X/submit_results",
        f"{CLIENT_ROUTE_PREFIX}/testrun/generic/X/finalize",
    ]
    # The terminal status/version payload is forwarded intact, and the run's
    # original finish time is injected from the record ts, which is in
    # milliseconds (5ms -> 0.005s).
    final_json = client.request.call_args.kwargs["json"]
    assert final_json["status"] == "passed"
    assert final_json["scylla_version"] == "6.2.0"
    assert final_json["end_time"] == 5 / 1000


async def test_finalize_end_time_is_injected_from_ts_when_absent():
    # ReplayRecord.ts is milliseconds (== _now_ns() // 1_000_000), so a ts of
    # 1_700_000_000_000ms must inject end_time == 1_700_000_000.0s.
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec(FINALIZE_ENDPOINT, ts=1_700_000_000_000,
                 location_params={"type": "generic", "id": "X"},
                 body={"status": "passed"}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    assert client.request.call_args.kwargs["json"]["end_time"] == 1_700_000_000.0


async def test_finalize_preserves_explicit_end_time_in_body():
    # A finalize record that already carries end_time is left untouched.
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec(FINALIZE_ENDPOINT, ts=5,
                 location_params={"type": "generic", "id": "X"},
                 body={"status": "passed", "end_time": 1234.5}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    assert client.request.call_args.kwargs["json"]["end_time"] == 1234.5


async def test_finalize_end_time_falls_back_to_last_seen_ts_when_own_ts_absent():
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
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    finalize_call = next(
        c for c in client.request.call_args_list
        if c.args[1].endswith("/finalize"))
    assert finalize_call.kwargs["json"]["end_time"] == 1_700_000_000.0


async def test_finalize_end_time_untouched_when_no_ts_anywhere_for_run():
    # No record for the run carries a ts at all -- end_time is left unset,
    # same as before this fallback existed, rather than injecting a bogus 0.
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec(FINALIZE_ENDPOINT, ts=0,
                 location_params={"type": "generic", "id": "X"},
                 body={"status": "passed"}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    assert "end_time" not in client.request.call_args.kwargs["json"]


async def test_finalize_runs_after_terminal_set_status():
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
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    urls = [c.args[1] for c in client.request.call_args_list]
    assert urls == [
        f"{CLIENT_ROUTE_PREFIX}/testrun/scylla-cluster-tests/X/set_status",
        f"{CLIENT_ROUTE_PREFIX}/testrun/scylla-cluster-tests/X/finalize",
    ]


async def test_non_terminal_set_status_keeps_natural_order():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/$id/set_status", ts=5,
                 location_params={"type": "t", "id": "X"},
                 body={"new_status": "running"}),
            _rec("/sct/$id/event/submit", ts=10,
                 location_params={"id": "X"}, body={"data": {}}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    urls = [c.args[1] for c in client.request.call_args_list]
    assert urls == [
        f"{CLIENT_ROUTE_PREFIX}/testrun/t/X/set_status",
        f"{CLIENT_ROUTE_PREFIX}/sct/X/event/submit",
    ]


async def test_heartbeats_collapse_to_last():
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
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    assert client.request.call_count == 1
    # The "last" heartbeat is the one with the highest ts (20).
    assert client.request.call_args.kwargs["json"] == {"hb": 2}


# ---------------------------------------------------------------------------
# URL reconstruction
# ---------------------------------------------------------------------------

async def test_url_substitutes_location_params():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/resource/$name/terminate", ts=1,
                 location_params={"id": "RUN", "name": "node-1"},
                 body={"reason": "manual"}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    assert client.request.call_args.args[1] == (
        f"{CLIENT_ROUTE_PREFIX}/sct/RUN/resource/node-1/terminate"
    )


async def test_double_slash_endpoint_is_normalised():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id//stress_cmd/submit", ts=1,
                 location_params={"id": "RUN"},
                 body={"cmd": "stress"}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    await _make_service(client).ingest(archive)
    assert client.request.call_args.args[1] == (
        f"{CLIENT_ROUTE_PREFIX}/sct/RUN/stress_cmd/submit"
    )


# ---------------------------------------------------------------------------
# auth header propagation
# ---------------------------------------------------------------------------

async def test_auth_header_is_forwarded():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=1,
                 location_params={"id": "X"}, body={"data": {}}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    svc = _make_service(client, auth_header="token abc")
    await svc.ingest(archive)
    assert client.request.call_args.kwargs["headers"] == {"Authorization": "token abc"}


# ---------------------------------------------------------------------------
# skip list
# ---------------------------------------------------------------------------

def test_finalize_is_not_in_skip_list():
    # finalize has no side effect outside Argus (it only writes the run row)
    # and is the sole terminal-state source for non-SCT plugins, so it must be
    # replayed, not skipped.
    assert FINALIZE_ENDPOINT not in SKIP_ENDPOINTS


@pytest.mark.parametrize("endpoint", sorted(SKIP_ENDPOINTS))
async def test_skip_endpoints_are_not_dispatched(endpoint: str):
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec(endpoint, ts=1, location_params={"id": "X", "type": "t"},
                 body={}),
        ],
    })
    client = AsyncMock()
    summary = await _make_service(client).ingest(archive)
    assert summary.skipped_no_replay == 1
    assert client.request.call_count == 0


# ---------------------------------------------------------------------------
# response handling
# ---------------------------------------------------------------------------

async def test_non_2xx_response_is_recorded_as_failure():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=1,
                 location_params={"id": "X"}, body={"data": {}}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(500, b"boom")
    summary = await _make_service(client).ingest(archive)
    assert summary.failed == 1
    assert summary.succeeded == 0
    assert "HTTP 500" in summary.errors[0]["error"]


async def test_2xx_envelope_error_is_recorded_as_failure():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=1,
                 location_params={"id": "X"}, body={"data": {}}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200, {
        "status": "error",
        "response": {"exception": "ValueError", "arguments": ["bad input"]},
    })
    summary = await _make_service(client).ingest(archive)
    assert summary.failed == 1
    assert "ValueError" in summary.errors[0]["error"]


async def test_client_open_exception_is_isolated():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=1, location_params={"id": "X"}, body={}),
            _rec("/sct/$id/event/submit", ts=2, location_params={"id": "Y"}, body={}),
        ],
    })
    client = AsyncMock()
    client.request.side_effect = [RuntimeError("kaboom"), _Response(200, b'{"status":"ok"}')]
    summary = await _make_service(client).ingest(archive)
    assert summary.failed == 1
    assert summary.succeeded == 1
    assert "RuntimeError" in summary.errors[0]["error"]


# ---------------------------------------------------------------------------
# dry_run
# ---------------------------------------------------------------------------

async def test_dry_run_does_not_dispatch():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/sct/$id/event/submit", ts=1, location_params={"id": "X"}, body={}),
            _rec("/testrun/$type/submit", ts=0,
                 location_params={"type": "generic"}, body={"run_id": "X"}),
        ],
    })
    client = AsyncMock()
    summary = await _make_service(client).ingest(archive, dry_run=True)
    assert summary.succeeded == 2
    assert client.request.call_count == 0


# ---------------------------------------------------------------------------
# create_missing_tests pre-step
# ---------------------------------------------------------------------------

async def test_create_missing_tests_invokes_hierarchy_on_submit_run():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "scylla-cluster-tests"},
                 body={"run_id": "550e8400-e29b-41d4-a716-446655440000",
                       "job_name": "scylla-staging/dusan/longevity-test",
                       "job_url": "https://jenkins.example/job/x"}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200, b'{"status":"ok"}')
    svc = _make_service(client, create_missing_tests=True)
    with patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure, \
         patch("argus.backend.service.client_service.ClientService"):
        summary = await svc.ingest(archive)
    assert summary.succeeded == 1
    ensure.assert_called_once()
    kwargs = ensure.call_args.kwargs
    assert kwargs["build_id"] == "scylla-staging/dusan/longevity-test"
    assert kwargs["plugin_name"] == "scylla-cluster-tests"


async def test_create_missing_tests_disabled_by_default():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "generic"},
                 body={"run_id": "x", "build_id": "scylla-master/perf"}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    svc = _make_service(client, create_missing_tests=False)
    # Patch the diagnosis to None (i.e. the test entity already exists) so
    # the dispatch path runs unchanged -- this test is about the auto-create
    # branch staying off, not about the pre-check.
    with patch.object(ReplayService, "_diagnose_missing_hierarchy", return_value=None), \
         patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure:
        summary = await svc.ingest(archive)
    ensure.assert_not_called()
    assert client.request.call_count == 1
    assert summary.succeeded == 1


async def test_missing_hierarchy_pre_check_fails_record_with_diagnosis():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "scylla-cluster-tests"},
                 body={"run_id": "abc",
                       "job_name": "scylla-staging/dusan/longevity-test"}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    svc = _make_service(client, create_missing_tests=False)
    diagnosis = (
        "test entity missing for build_id='scylla-staging/dusan/longevity-test': "
        "would create release='scylla-staging', group='dusan', test='longevity-test'; "
        "currently missing: release, group, test. ..."
    )
    with patch.object(ReplayService, "_diagnose_missing_hierarchy", return_value=diagnosis):
        summary = await svc.ingest(archive)
    assert client.request.call_count == 0  # dispatch was blocked
    assert summary.failed == 1
    assert summary.succeeded == 0
    assert len(summary.errors) == 1
    assert summary.errors[0]["endpoint"] == "/testrun/$type/submit"
    assert summary.errors[0]["error"] == diagnosis


async def test_missing_hierarchy_pre_check_runs_in_dry_run():
    """dry_run still surfaces the diagnosis so users can preview what would
    fail without uploading -- the whole point of dry_run."""
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "generic"},
                 body={"run_id": "x", "job_name": "some/job"}),
        ],
    })
    client = AsyncMock()
    svc = _make_service(client, create_missing_tests=False)
    with patch.object(ReplayService, "_diagnose_missing_hierarchy", return_value="diag"):
        summary = await svc.ingest(archive, dry_run=True)
    assert client.request.call_count == 0
    assert summary.failed == 1
    assert summary.errors[0]["error"] == "diag"


async def test_pre_check_exception_does_not_block_dispatch():
    """If the pre-check itself raises (e.g. transient DB error), the dispatch
    still runs -- pre-check failures must never harden into outages."""
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "generic"},
                 body={"run_id": "x", "job_name": "some/job"}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    svc = _make_service(client, create_missing_tests=False)
    with patch.object(
        ReplayService, "_diagnose_missing_hierarchy",
        side_effect=RuntimeError("db down"),
    ):
        summary = await svc.ingest(archive)
    assert client.request.call_count == 1
    assert summary.succeeded == 1


async def test_create_missing_tests_failure_does_not_abort_dispatch():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "scylla-cluster-tests"},
                 body={"run_id": "x", "job_name": "scylla-staging/dusan/lt"}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200, b'{"status":"ok"}')
    svc = _make_service(client, create_missing_tests=True)
    with patch(
        "argus.backend.service.test_hierarchy.ensure_test_hierarchy",
        side_effect=RuntimeError("db down"),
    ) as ensure:
        summary = await svc.ingest(archive)
    ensure.assert_called_once()
    assert client.request.call_count == 1  # dispatch still ran
    assert summary.succeeded == 1


async def test_create_missing_tests_skips_when_no_build_id_in_body():
    archive = _make_archive({
        "argus_replay_log_r_1.jsonl": [
            _rec("/testrun/$type/submit", ts=1,
                 location_params={"type": "sirenada"},
                 body={"run_id": "x"}),
        ],
    })
    client = AsyncMock()
    client.request.return_value = _Response(200)
    svc = _make_service(client, create_missing_tests=True)
    with patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure:
        await svc.ingest(archive)
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
    test_mock.DoesNotExist = web.DocumentNotFound
    if test_exists:
        test_mock.get = AsyncMock(return_value=MagicMock())
    else:
        test_mock.get = AsyncMock(side_effect=web.DocumentNotFound)

    release_mock = MagicMock()
    release_mock.DoesNotExist = web.DocumentNotFound
    if release_exists:
        rel = MagicMock(id="rel-id")
        release_mock.get = AsyncMock(return_value=rel)
    else:
        release_mock.get = AsyncMock(side_effect=web.DocumentNotFound)

    group_mock = MagicMock()
    if release_exists and group_exists:
        g = MagicMock(build_system_id="scylla-staging/dusan")
        group_mock.find.return_value.all = AsyncMock(return_value=[g])
    else:
        group_mock.find.return_value.all = AsyncMock(return_value=[])

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


async def test_diagnose_returns_none_when_test_exists():
    patcher, _ = _patch_hierarchy_models(test_exists=True)
    with patcher:
        result = await ReplayService._diagnose_missing_hierarchy(
            _submit_record("scylla-staging/dusan/longevity-test")
        )
    assert result is None


async def test_diagnose_returns_none_when_no_build_id():
    # No DB lookup should be attempted; safe to call without patching models.
    assert await ReplayService._diagnose_missing_hierarchy(
        _rec("/testrun/$type/submit", ts=1,
             location_params={"type": "generic"},
             body={"run_id": "abc"})
    ) is None


async def test_diagnose_reports_all_three_missing_when_release_absent():
    patcher, _ = _patch_hierarchy_models(test_exists=False, release_exists=False)
    with patcher:
        result = await ReplayService._diagnose_missing_hierarchy(
            _submit_record("scylla-staging/dusan/longevity-test")
        )
    assert result is not None
    assert "release='scylla-staging'" in result
    assert "group='dusan'" in result
    assert "test='longevity-test'" in result
    assert "currently missing: release, group, test" in result
    assert "--create-missing-tests" in result


async def test_diagnose_reports_group_and_test_missing_when_only_release_exists():
    patcher, _ = _patch_hierarchy_models(
        test_exists=False, release_exists=True, group_exists=False,
    )
    with patcher:
        result = await ReplayService._diagnose_missing_hierarchy(
            _submit_record("scylla-staging/dusan/longevity-test")
        )
    assert result is not None
    assert "currently missing: group, test" in result


async def test_diagnose_reports_only_test_missing_when_release_and_group_exist():
    patcher, _ = _patch_hierarchy_models(
        test_exists=False, release_exists=True, group_exists=True,
    )
    with patcher:
        result = await ReplayService._diagnose_missing_hierarchy(
            _submit_record("scylla-staging/dusan/longevity-test")
        )
    assert result is not None
    assert "currently missing: test" in result
    # Make sure we didn't accidentally mark release or group as missing too.
    assert "release," not in result.split("currently missing:")[1]
    assert "group," not in result.split("currently missing:")[1]


async def test_diagnose_parses_two_segment_build_id():
    """``release/test`` form: group becomes ``<release>-root`` per
    parse_build_id; group's build_system_id is the release name."""
    patcher, _ = _patch_hierarchy_models(test_exists=False, release_exists=False)
    with patcher:
        result = await ReplayService._diagnose_missing_hierarchy(
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


async def test_backfill_submits_only_missing_s3_objects():
    recorded = f"{_RUN_ID}/20260526_115014/db-node-0-1-15bb6cad.tar.zst"
    loader = f"{_RUN_ID}/20260526_115014/loader-set-15bb6cad.tar.zst"
    runner = f"{_RUN_ID}/20260526_115014/sct-runner-events-15bb6cad.tar.zst"
    s3 = _mock_s3([recorded, loader, runner])

    client = AsyncMock()
    client.request.return_value = _Response(200, b'{"status":"ok"}')
    service = _make_service(client, backfill_logs=True, s3_client=s3)
    summary = await service.ingest(_logs_archive([recorded]))

    # Listed the run's prefix once.
    s3.list_objects_v2.assert_called_once()
    assert s3.list_objects_v2.call_args.kwargs["Prefix"] == f"{_RUN_ID}/"

    # Two dispatches: the recorded logs/submit + one back-fill logs/submit.
    bodies = [c.kwargs["json"] for c in client.request.call_args_list]
    backfill_bodies = [b for b in bodies if b and any(
        "loader-set" in l["log_name"] or "sct-runner" in l["log_name"] for l in b.get("logs", []))]
    assert len(backfill_bodies) == 1
    submitted = {l["log_link"] for l in backfill_bodies[0]["logs"]}
    # Only the two *missing* archives, never the already-recorded db-node link.
    assert submitted == {_s3_url(loader), _s3_url(runner)}
    assert _s3_url(recorded) not in submitted
    assert summary.backfilled_logs == 2


async def test_backfill_can_be_disabled():
    # The ingest endpoint enables backfill by default; passing backfill_logs=False
    # (?backfill_logs=false) must suppress the S3 listing entirely.
    recorded = f"{_RUN_ID}/20260526_115014/db-node-0-1-15bb6cad.tar.zst"
    loader = f"{_RUN_ID}/20260526_115014/loader-set-15bb6cad.tar.zst"
    s3 = _mock_s3([recorded, loader])

    client = AsyncMock()
    client.request.return_value = _Response(200, b'{"status":"ok"}')
    service = _make_service(client, backfill_logs=False, s3_client=s3)
    summary = await service.ingest(_logs_archive([recorded]))

    s3.list_objects_v2.assert_not_called()
    assert summary.backfilled_logs == 0


async def test_backfill_noop_when_all_logs_already_present():
    recorded = f"{_RUN_ID}/20260526_115014/db-node-0-1-15bb6cad.tar.zst"
    s3 = _mock_s3([recorded])  # S3 has nothing new

    client = AsyncMock()
    client.request.return_value = _Response(200, b'{"status":"ok"}')
    service = _make_service(client, backfill_logs=True, s3_client=s3)
    summary = await service.ingest(_logs_archive([recorded]))

    assert summary.backfilled_logs == 0
    # Only the single recorded logs/submit was dispatched.
    assert client.request.call_count == 1


async def test_backfill_skipped_on_dry_run():
    recorded = f"{_RUN_ID}/20260526_115014/db-node-0-1-15bb6cad.tar.zst"
    loader = f"{_RUN_ID}/20260526_115014/loader-set-15bb6cad.tar.zst"
    s3 = _mock_s3([recorded, loader])

    service = _make_service(backfill_logs=True, s3_client=s3)
    summary = await service.ingest(_logs_archive([recorded]), dry_run=True)

    s3.list_objects_v2.assert_not_called()
    assert summary.backfilled_logs == 0


async def test_backfill_falls_back_to_sct_default_bucket_when_no_bucket_derivable():
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
    summary = await service.ingest(archive)

    s3.list_objects_v2.assert_called_once_with(Bucket=_BUCKET, Prefix=f"{_RUN_ID}/")
    assert summary.backfilled_logs == 1


def test_log_name_from_key_strips_archive_suffix():
    assert ReplayService._log_name_from_key(
        f"{_RUN_ID}/ts/loader-set-15bb6cad.tar.zst") == "loader-set-15bb6cad"
    assert ReplayService._log_name_from_key(
        f"{_RUN_ID}/ts/history.jsonl.tar.gz") == "history.jsonl"
    assert ReplayService._log_name_from_key(f"{_RUN_ID}/ts/plain.log") == "plain.log"


# ---------------------------------------------------------------------------
# retargeting (build_id), build numbers, resume, and the stamp step
# ---------------------------------------------------------------------------

_NEW_BUILD_ID = "scylla-staging/jdoe/my-argus-local-run"
_OWNER = SimpleNamespace(id=UUID("11111111-1111-1111-1111-111111111111"), username="jdoe")
_RESUME_ID = "22222222-2222-2222-2222-222222222222"
_TEST_ID = UUID("44444444-4444-4444-4444-444444444444")


def _run_archive(log_keys: list[str] | None = None, run_id: str = _RUN_ID) -> list[dict]:
    """A Jenkins run: a submit_run, an event that names the run in its body,
    and a logs/submit."""
    return [
        _rec("/testrun/$type/submit", ts=1,
             location_params={"type": "scylla-cluster-tests"},
             body={"run_id": run_id, "job_name": "scylla-master/longevity/longevity-100gb-4h",
                   "job_url": "https://jenkins.scylladb.com/job/scylla-master/job/longevity/12/",
                   "started_by": "linux_user=jdoe"}),
        _rec("/sct/$id/event/submit", ts=2,
             location_params={"id": run_id},
             body={"data": {"run_id": run_id, "message": f"run {run_id} started"}}),
        _rec("/testrun/$type/$id/logs/submit", ts=3,
             location_params={"type": "scylla-cluster-tests", "id": run_id},
             body={"logs": [{"log_name": k.rsplit("/", 1)[-1], "log_link": _s3_url(k)}
                            for k in (log_keys or [])]}),
    ]


def _archive(*runs: list[dict]) -> bytes:
    return _make_archive({"argus_replay_log_run.jsonl": [r for run in runs for r in run]})


def _dispatched(client) -> list[tuple[str, dict]]:
    return [(c.args[1], c.kwargs["json"]) for c in client.request.call_args_list]


def _ok_client():
    client = AsyncMock()
    client.request.return_value = _Response(200, b'{"status":"ok"}')
    return client


class _StoredRun:
    """A stored SCT run: the fields the stamp step reads and writes."""

    model_fields = {"started_by": None}

    def __init__(self):
        self.id = UUID(_RUN_ID)
        self.test_id = _TEST_ID
        self.build_id = _NEW_BUILD_ID
        self.build_number = 3
        self.source_run_id = None
        self.assignee = None
        self.started_by = "linux_user=jdoe"
        self.save = AsyncMock()


class _StoredRunWithoutStarter(_StoredRun):
    """A stored run of a plugin whose model has no started_by field."""

    model_fields = {}


@pytest.fixture
def run_store():
    """The release and the test entity exist, the build path holds
    builds #1 and #4, and every run model read returns one stored run."""
    run = _StoredRun()
    model = MagicMock()
    model.get = AsyncMock(return_value=run)
    model.find.return_value.only.return_value.values_list.return_value.all = AsyncMock(
        return_value=[(1,), (4,), (None,)])
    reservations = MagicMock()
    reservations.reserve = AsyncMock(return_value=True)
    reservations.take_over = AsyncMock(return_value=False)
    with patch.object(ReplayService, "_check_release", AsyncMock()), \
         patch.object(ReplayService, "_diagnose_missing_hierarchy", return_value=None), \
         patch.object(ReplayService, "_run_models", return_value=[model]), \
         patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy"), \
         patch("argus.backend.service.replay_service.ReplayBuildNumber", reservations), \
         patch("argus.backend.service.replay_service.TestRunService") as testrun_cls, \
         patch("argus.backend.service.replay_service.ClientService") as service_cls:
        service_cls.return_value.get_model.return_value = model
        testrun_cls.return_value.change_run_assignee = AsyncMock()
        yield SimpleNamespace(run=run, model=model, service_cls=service_cls, reservations=reservations,
                              change_assignee=testrun_cls.return_value.change_run_assignee)


async def test_runs_listed_without_build_id(run_store):
    summary = await _make_service().ingest(_archive(_run_archive()))

    assert summary.runs == [{"type": "scylla-cluster-tests", "id": _RUN_ID, "source_id": _RUN_ID,
                             "build_id": None, "build_number": None}]
    assert summary.as_dict()["runs"] == summary.runs


async def test_build_id_moves_every_record_to_a_new_run(run_store):
    client = _ok_client()
    summary = await _make_service(client, build_id=_NEW_BUILD_ID).ingest(_archive(_run_archive()))

    assert len(summary.runs) == 1
    new_id = summary.runs[0]["id"]
    assert new_id != _RUN_ID
    assert summary.runs[0]["source_id"] == _RUN_ID

    (submit_url, submit_body), (event_url, event_body), (logs_url, _) = _dispatched(client)
    assert submit_url == f"{CLIENT_ROUTE_PREFIX}/testrun/scylla-cluster-tests/submit"
    assert submit_body["run_id"] == new_id
    assert submit_body["job_name"] == _NEW_BUILD_ID
    assert event_url == f"{CLIENT_ROUTE_PREFIX}/sct/{new_id}/event/submit"
    assert event_body["data"]["run_id"] == new_id
    # Only whole-value matches change: free text that mentions the run stays as recorded.
    assert event_body["data"]["message"] == f"run {_RUN_ID} started"
    assert logs_url == f"{CLIENT_ROUTE_PREFIX}/testrun/scylla-cluster-tests/{new_id}/logs/submit"


_NEW_BUILD_URL = f"https://argus.example.com/test/{_NEW_BUILD_ID}/5/"


@pytest.mark.parametrize(("body", "expected"), [
    ({"job_name": "local_run", "job_url": "https://jenkins/job/x/7"},
     {"job_name": _NEW_BUILD_ID, "job_url": _NEW_BUILD_URL}),
    ({"build_id": "local/dtest", "build_url": "https://jenkins/job/y/2"},
     {"build_id": _NEW_BUILD_ID, "build_url": _NEW_BUILD_URL}),
    ({"build_id": "local/sirenada", "build_job_url": "https://jenkins/job/z/9"},
     {"build_id": _NEW_BUILD_ID, "build_job_url": _NEW_BUILD_URL}),
])
async def test_build_id_refiles_submit_under_the_plugin_keys(run_store, body, expected):
    client = _ok_client()
    archive = _archive([_rec("/testrun/$type/submit", ts=1, location_params={"type": "generic"},
                             body={"run_id": _RUN_ID, **body})])

    service = _make_service(client, build_id=_NEW_BUILD_ID)
    service._argus_url = "https://argus.example.com"
    await service.ingest(archive)

    submit_body = _dispatched(client)[0][1]
    assert {k: submit_body[k] for k in expected} == expected


async def test_build_id_gives_a_new_run_on_each_ingest(run_store):
    first = await _make_service(build_id=_NEW_BUILD_ID).ingest(_archive(_run_archive()))
    second = await _make_service(build_id=_NEW_BUILD_ID).ingest(_archive(_run_archive()))

    assert first.runs[0]["id"] != second.runs[0]["id"]


async def test_build_id_backfill_lists_the_original_s3_prefix(run_store):
    recorded = f"{_RUN_ID}/20260526_115014/db-node-0-1-15bb6cad.tar.zst"
    loader = f"{_RUN_ID}/20260526_115014/loader-set-15bb6cad.tar.zst"
    s3 = _mock_s3([recorded, loader])
    client = _ok_client()

    summary = await _make_service(
        client, build_id=_NEW_BUILD_ID, backfill_logs=True, s3_client=s3,
    ).ingest(_archive(_run_archive([recorded])))

    s3.list_objects_v2.assert_called_once_with(Bucket=_BUCKET, Prefix=f"{_RUN_ID}/")
    new_id = summary.runs[0]["id"]
    backfill_url, backfill_body = _dispatched(client)[-1]
    assert backfill_url == f"{CLIENT_ROUTE_PREFIX}/testrun/scylla-cluster-tests/{new_id}/logs/submit"
    assert [log["log_link"] for log in backfill_body["logs"]] == [_s3_url(loader)]
    assert summary.backfilled_logs == 1


@pytest.mark.parametrize("build_id", [
    "", "my-argus-local-run", "/scylla-staging/x", "scylla-staging//x", "scylla-staging/my run", "a/b/",
    "a/b#", "a/b#0", "a/b#07", "a/b#-1", "a/b#x", "a#3",
])
async def test_build_id_must_name_a_release_and_a_test(build_id: str):
    client = _ok_client()
    with pytest.raises(DataValidationError):
        await _make_service(client, build_id=build_id).ingest(_archive(_run_archive()))
    client.request.assert_not_called()


async def test_build_number_takes_the_next_free_number(run_store):
    summary = await _make_service(build_id=_NEW_BUILD_ID).ingest(_archive(_run_archive()))

    run_store.model.find.assert_called_with(build_id=_NEW_BUILD_ID)
    assert summary.runs[0]["build_id"] == _NEW_BUILD_ID
    assert summary.runs[0]["build_number"] == 5


async def test_build_number_counts_up_for_each_run(run_store):
    other = "33333333-3333-3333-3333-333333333333"
    summary = await _make_service(build_id=_NEW_BUILD_ID).ingest(
        _archive(_run_archive(), _run_archive(run_id=other)))

    assert [r["build_number"] for r in summary.runs] == [5, 6]


async def test_build_number_starts_at_the_given_number(run_store):
    summary = await _make_service(build_id=f"{_NEW_BUILD_ID}#7").ingest(_archive(_run_archive()))

    assert summary.runs[0]["build_id"] == _NEW_BUILD_ID
    assert summary.runs[0]["build_number"] == 7


async def test_build_number_given_must_be_free(run_store):
    client = _ok_client()
    with pytest.raises(DataValidationError, match="#4 exists"):
        await _make_service(client, build_id=f"{_NEW_BUILD_ID}#4").ingest(_archive(_run_archive()))
    client.request.assert_not_called()


async def test_build_number_is_shown_on_dry_run(run_store):
    summary = await _make_service(build_id=_NEW_BUILD_ID).ingest(_archive(_run_archive()), dry_run=True)

    assert summary.runs[0]["build_number"] == 5
    run_store.run.save.assert_not_awaited()


async def test_unknown_run_type_is_a_validation_error():
    archive = _archive([_rec("/testrun/$type/submit", ts=1, location_params={"type": "no-such-plugin"},
                             body={"run_id": _RUN_ID, "job_name": "x"})])
    with patch.object(ReplayService, "_check_release", AsyncMock()), \
         pytest.raises(DataValidationError, match="no-such-plugin"):
        await _make_service(build_id=_NEW_BUILD_ID).ingest(archive)


async def test_copy_is_created_with_its_build_number(run_store):
    client = _ok_client()
    await _make_service(client, build_id=_NEW_BUILD_ID).ingest(_archive(_run_archive()))

    # The plugin reads the build number from the build URL when it creates the run.
    assert _dispatched(client)[0][1]["job_url"] == f"/test/{_NEW_BUILD_ID}/5/"


async def test_copy_records_its_source_right_after_submit(run_store):
    client = _ok_client()
    source_at_event = []

    async def request(method, url, **kwargs):
        if "/event/submit" in url:
            source_at_event.append(run_store.run.source_run_id)
        return _Response(200, b'{"status":"ok"}')

    client.request.side_effect = request
    summary = await _make_service(client, build_id=_NEW_BUILD_ID).ingest(_archive(_run_archive()))

    # A replay that stops after submit_run leaves a run that --resume accepts.
    assert source_at_event == [UUID(_RUN_ID)]
    assert str(run_store.model.get.call_args.kwargs["id"]) == summary.runs[0]["id"]
    # No owner: the assignee and the starter stay as the replay created them.
    assert run_store.run.assignee is None
    assert run_store.run.started_by == "linux_user=jdoe"
    run_store.run.save.assert_awaited_once()


async def test_copy_belongs_to_the_owner(run_store):
    client = _ok_client()
    await _make_service(client, build_id=_NEW_BUILD_ID, caller=_OWNER, as_me=True).ingest(_archive(_run_archive()))

    # The copy is created with the owner as its starter, set in one place.
    assert _dispatched(client)[0][1]["started_by"] == "jdoe"
    assert run_store.run.assignee == _OWNER.id
    assert run_store.run.started_by == "linux_user=jdoe"
    run_store.change_assignee.assert_not_called()


async def test_copy_of_a_plugin_without_started_by_keeps_its_fields(run_store):
    run_store.model.get.return_value = run = _StoredRunWithoutStarter()
    client = _ok_client()
    archive = _archive([_rec("/testrun/$type/submit", ts=1, location_params={"type": "driver-matrix-tests"},
                             body={"run_id": _RUN_ID, "job_name": "x", "job_url": ""})])

    summary = await _make_service(client, build_id=_NEW_BUILD_ID, caller=_OWNER, as_me=True).ingest(archive)

    assert "started_by" not in _dispatched(client)[0][1]
    assert run.assignee == _OWNER.id
    assert run.started_by == "linux_user=jdoe"
    assert summary.errors == []


async def test_owner_without_build_id_changes_only_the_assignee(run_store):
    client = _ok_client()
    summary = await _make_service(client, caller=_OWNER, as_me=True).ingest(_archive(_run_archive()))

    # The original run keeps its recorded starter.
    assert _dispatched(client)[0][1]["started_by"] == "linux_user=jdoe"
    run_store.change_assignee.assert_awaited_once_with(
        test_id=_TEST_ID, run_id=UUID(_RUN_ID), new_assignee=_OWNER.id, user=_OWNER)
    assert run_store.run.started_by == "linux_user=jdoe"
    assert run_store.run.source_run_id is None
    run_store.run.save.assert_not_awaited()
    assert summary.errors == []


async def test_owner_who_is_already_the_assignee_changes_nothing(run_store):
    run_store.run.assignee = _OWNER.id

    summary = await _make_service(caller=_OWNER, as_me=True).ingest(_archive(_run_archive()))

    run_store.change_assignee.assert_not_called()
    assert summary.errors == []


async def test_owner_without_build_id_needs_a_test(run_store):
    run_store.run.test_id = None

    summary = await _make_service(caller=_OWNER, as_me=True).ingest(_archive(_run_archive()))

    run_store.change_assignee.assert_not_called()
    assert [e["endpoint"] for e in summary.errors] == ["stamp_run"]


async def test_stamp_skipped_without_build_id_and_owner(run_store):
    await _make_service().ingest(_archive(_run_archive()))

    run_store.service_cls.return_value.get_model.assert_not_called()


async def test_stamp_failure_is_reported_per_run(run_store):
    run_store.model.get.side_effect = DocumentNotFound("gone")

    summary = await _make_service(caller=_OWNER, as_me=True).ingest(_archive(_run_archive()))

    assert [e["endpoint"] for e in summary.errors] == ["stamp_run"]
    assert _RUN_ID in summary.errors[0]["error"]


async def test_owner_skipped_on_dry_run(run_store):
    await _make_service(caller=_OWNER, as_me=True).ingest(_archive(_run_archive()), dry_run=True)

    run_store.service_cls.return_value.get_model.assert_not_called()


async def test_stamp_skips_a_run_whose_submit_failed(run_store):
    diagnosis = "test entity missing for build_id='scylla-staging/jdoe/my-argus-local-run'"
    with patch.object(ReplayService, "_diagnose_missing_hierarchy", return_value=diagnosis):
        summary = await _make_service(caller=_OWNER, as_me=True, build_id=_NEW_BUILD_ID).ingest(_archive(_run_archive()))

    run_store.model.get.assert_not_called()
    assert [e["endpoint"] for e in summary.errors] == ["/testrun/$type/submit"]


async def test_resume_reuses_the_given_run_id_and_build(run_store):
    run_store.run.source_run_id = UUID(_RUN_ID)
    client = _ok_client()

    summary = await _make_service(
        client, build_id=_NEW_BUILD_ID, resume_run_id=UUID(_RESUME_ID),
    ).ingest(_archive(_run_archive()))

    assert summary.runs == [{"type": "scylla-cluster-tests", "id": _RESUME_ID, "source_id": _RUN_ID,
                             "build_id": _NEW_BUILD_ID, "build_number": 3}]
    # The run exists: submit_run is skipped, since some plugins append its results again.
    urls = [url for url, _ in _dispatched(client)]
    assert not any(url.endswith("/testrun/scylla-cluster-tests/submit") for url in urls)
    assert urls[0] == f"{CLIENT_ROUTE_PREFIX}/sct/{_RESUME_ID}/event/submit"
    assert summary.skipped_no_replay == 1
    assert str(run_store.model.get.await_args_list[0].kwargs["id"]) == _RESUME_ID
    run_store.reservations.reserve.assert_not_called()


async def test_resume_with_the_run_build_number(run_store):
    run_store.run.source_run_id = UUID(_RUN_ID)

    summary = await _make_service(build_id=f"{_NEW_BUILD_ID}#3", resume_run_id=UUID(_RESUME_ID)).ingest(
        _archive(_run_archive()))

    assert summary.runs[0]["build_number"] == 3


async def test_resume_with_another_build_number_fails(run_store):
    run_store.run.source_run_id = UUID(_RUN_ID)

    with pytest.raises(DataValidationError, match="is build #3, not #8"):
        await _make_service(build_id=f"{_NEW_BUILD_ID}#8", resume_run_id=UUID(_RESUME_ID)).ingest(
            _archive(_run_archive()))


async def test_resume_needs_build_id(run_store):
    with pytest.raises(DataValidationError, match="needs build_id"):
        await _make_service(resume_run_id=UUID(_RESUME_ID)).ingest(_archive(_run_archive()))


async def test_resume_needs_one_run(run_store):
    other = "33333333-3333-3333-3333-333333333333"
    with pytest.raises(DataValidationError, match="one run"):
        await _make_service(build_id=_NEW_BUILD_ID, resume_run_id=UUID(_RESUME_ID)).ingest(
            _archive(_run_archive(), _run_archive(run_id=other)))


async def test_resume_run_must_exist(run_store):
    run_store.model.get.side_effect = DocumentNotFound("gone")
    with pytest.raises(DataValidationError, match="does not exist"):
        await _make_service(build_id=_NEW_BUILD_ID, resume_run_id=UUID(_RESUME_ID)).ingest(
            _archive(_run_archive()))


@pytest.mark.parametrize(("source_run_id", "build_id"), [
    (None, _NEW_BUILD_ID),
    ("33333333-3333-3333-3333-333333333333", _NEW_BUILD_ID),
    (_RUN_ID, "scylla-staging/jdoe/other-run"),
])
async def test_resume_run_must_be_a_copy_of_this_run_in_this_path(run_store, source_run_id, build_id):
    run_store.run.source_run_id = UUID(source_run_id) if source_run_id else None
    run_store.run.build_id = build_id
    client = _ok_client()

    with pytest.raises(DataValidationError, match="is not a replay of run"):
        await _make_service(client, build_id=_NEW_BUILD_ID, resume_run_id=UUID(_RESUME_ID)).ingest(
            _archive(_run_archive()))
    client.request.assert_not_called()


# ---------------------------------------------------------------------------
# defaults: the local-runs path, as_me and create_missing_tests
# ---------------------------------------------------------------------------

_LOCAL_PATH = "local-runs/jdoe/longevity-100gb-4h"


def _local_archive(**submit_body) -> bytes:
    body = {"run_id": _RUN_ID, "job_name": "local_run", "job_url": "", "started_by": "linux_user=jdoe",
            "sct_config": {"config_files": ["test-cases/longevity/longevity-100gb-4h.yaml",
                                            "configurations/minicloud/cs-baseline.yaml"]}}
    body.update(submit_body)
    return _archive([_rec("/testrun/$type/submit", ts=1, location_params={"type": "scylla-cluster-tests"},
                          body=body)])


async def test_local_run_goes_to_local_runs_of_the_caller(run_store):
    client = _ok_client()
    summary = await _make_service(client, caller=_OWNER, local_runs=True, create_missing_tests=None).ingest(_local_archive())

    assert summary.runs[0]["build_id"] == _LOCAL_PATH
    assert summary.runs[0]["build_number"] == 5
    assert summary.runs[0]["id"] != _RUN_ID
    submit_body = _dispatched(client)[0][1]
    assert submit_body["job_name"] == _LOCAL_PATH
    # The copy belongs to the caller by default.
    assert submit_body["started_by"] == "jdoe"
    assert run_store.run.assignee == _OWNER.id


async def test_local_run_creates_its_folders_by_default(run_store):
    with patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure:
        await _make_service(caller=_OWNER, local_runs=True, create_missing_tests=None).ingest(_local_archive())

    assert ensure.call_args.kwargs["build_id"] == _LOCAL_PATH


async def test_build_id_creates_no_folders_by_default(run_store):
    diagnosis = "test entity missing for build_id='scylla-staging/new-group/new-test'"
    with patch.object(ReplayService, "_diagnose_missing_hierarchy", return_value=diagnosis), \
         patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure:
        summary = await _make_service(build_id="scylla-staging/new-group/new-test", create_missing_tests=None).ingest(
            _archive(_run_archive()))

    ensure.assert_not_called()
    assert summary.errors[0]["error"] == diagnosis


async def test_build_id_creates_folders_when_asked(run_store):
    with patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure:
        await _make_service(build_id="scylla-staging/new-group/new-test", create_missing_tests=True).ingest(
            _archive(_run_archive()))

    assert ensure.call_args.kwargs["build_id"] == "scylla-staging/new-group/new-test"


async def test_local_run_defaults_can_be_turned_off(run_store):
    client = _ok_client()
    await _make_service(client, caller=_OWNER, local_runs=True, as_me=False, create_missing_tests=False).ingest(
        _local_archive())

    submit_body = _dispatched(client)[0][1]
    assert submit_body["job_name"] == _LOCAL_PATH
    assert submit_body["started_by"] == "linux_user=jdoe"
    assert run_store.run.assignee is None


async def test_build_id_overrides_the_local_path(run_store):
    summary = await _make_service(caller=_OWNER, local_runs=True, build_id="scylla-staging/jdoe/x").ingest(_local_archive())

    assert summary.runs[0]["build_id"] == "scylla-staging/jdoe/x"


async def test_jenkins_run_keeps_its_recorded_path(run_store):
    client = _ok_client()
    summary = await _make_service(client, caller=_OWNER, local_runs=True, create_missing_tests=None).ingest(
        _local_archive(job_name="scylla-master/longevity/longevity-100gb-4h",
                       job_url="https://jenkins.scylladb.com/job/scylla-master/job/longevity/12/"))

    assert summary.runs[0]["id"] == _RUN_ID
    assert summary.runs[0]["build_id"] is None
    assert _dispatched(client)[0][1]["job_name"] == "scylla-master/longevity/longevity-100gb-4h"
    # Not a copy: the caller owns it only when asking for it.
    run_store.change_assignee.assert_not_called()


async def test_archive_of_two_runs_keeps_its_recorded_paths(run_store):
    other = "33333333-3333-3333-3333-333333333333"
    summary = await _make_service(caller=_OWNER, local_runs=True).ingest(
        _archive(_run_archive(), _run_archive(run_id=other)))

    assert [r["build_id"] for r in summary.runs] == [None, None]


@pytest.mark.parametrize(("body", "job"), [
    ({"sct_config": {"config_files": "test-cases/a/longevity-50gb.yaml other.yaml"}}, "longevity-50gb"),
    ({"sct_config": {"config_files": ["x/My Test (v2).yml"]}}, "My-Test-v2"),
    ({"sct_config": {}, "job_name": "local/dtest-nightly"}, "dtest-nightly"),
    ({"sct_config": None, "job_name": "", "build_id": "my run"}, "my-run"),
    ({"sct_config": None, "job_name": ""}, "local-run"),
])
async def test_local_job_name(body, job):
    assert ReplayService._local_job_name(body) == job


async def test_local_path_cleans_the_username(run_store):
    caller = SimpleNamespace(id=_OWNER.id, username="John Doe")
    summary = await _make_service(caller=caller, local_runs=True).ingest(_local_archive())

    assert summary.runs[0]["build_id"] == "local-runs/John-Doe/longevity-100gb-4h"


async def test_local_run_can_resume(run_store):
    run_store.run.source_run_id = UUID(_RUN_ID)
    run_store.run.build_id = _LOCAL_PATH

    summary = await _make_service(caller=_OWNER, local_runs=True, resume_run_id=UUID(_RESUME_ID)).ingest(
        _local_archive())

    assert summary.runs[0]["id"] == _RESUME_ID
    assert summary.runs[0]["build_number"] == 3


# ---------------------------------------------------------------------------
# keep_run and the release rule
# ---------------------------------------------------------------------------

async def test_local_run_replays_as_recorded_without_local_runs(run_store):
    # An older CLI, or any other client, sends no local_runs and gets the replay it always got.
    client = _ok_client()
    summary = await _make_service(client, caller=_OWNER).ingest(_local_archive())

    assert summary.runs[0]["id"] == _RUN_ID
    assert summary.runs[0]["build_id"] is None
    assert _dispatched(client)[0][1]["job_name"] == "local_run"


async def test_explicit_build_id_needs_an_existing_release():
    client = _ok_client()
    with patch("argus.backend.models.web.ArgusRelease.get", AsyncMock(side_effect=DocumentNotFound("x"))), \
         patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure:
        with pytest.raises(DataValidationError, match="'scylla-stagign' .* does not exist"):
            await _make_service(client, build_id="scylla-stagign/jdoe/x", create_missing_tests=None).ingest(
                _archive(_run_archive()))
    client.request.assert_not_called()
    ensure.assert_not_called()


async def test_explicit_build_id_with_an_existing_release_passes():
    with patch("argus.backend.models.web.ArgusRelease.get", AsyncMock(return_value=MagicMock())) as get:
        await ReplayService._check_release(_NEW_BUILD_ID)
    get.assert_awaited_once_with(name="scylla-staging")


async def test_local_runs_default_may_create_its_release(run_store):
    run_store_check = AsyncMock()
    with patch.object(ReplayService, "_check_release", run_store_check), \
         patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure:
        await _make_service(caller=_OWNER, local_runs=True, create_missing_tests=None).ingest(_local_archive())

    run_store_check.assert_not_called()
    assert ensure.call_args.kwargs["build_id"] == _LOCAL_PATH


# ---------------------------------------------------------------------------
# build number reservation, URL hygiene and robustness
# ---------------------------------------------------------------------------

async def test_build_number_is_reserved_before_the_run_exists(run_store):
    summary = await _make_service(build_id=_NEW_BUILD_ID).ingest(_archive(_run_archive()))

    run_store.reservations.reserve.assert_awaited_once_with(
        _NEW_BUILD_ID, 5, UUID(summary.runs[0]["id"]))


async def test_build_number_skips_a_number_another_replay_reserved(run_store):
    # Another replay won #5 between the read and the reservation.
    run_store.reservations.reserve.side_effect = [False, True]
    client = _ok_client()

    summary = await _make_service(client, build_id=_NEW_BUILD_ID).ingest(_archive(_run_archive()))

    assert summary.runs[0]["build_number"] == 6
    assert _dispatched(client)[0][1]["job_url"].endswith("/6/")


async def test_build_number_takes_over_the_reservation_of_a_failed_replay(run_store):
    # #5 is reserved, no run holds it, and the reservation is past its grace period.
    run_store.reservations.reserve.return_value = False
    run_store.reservations.take_over.return_value = True

    summary = await _make_service(build_id=f"{_NEW_BUILD_ID}#5").ingest(_archive(_run_archive()))

    assert summary.runs[0]["build_number"] == 5
    run_store.reservations.take_over.assert_awaited_once_with(_NEW_BUILD_ID, 5, UUID(summary.runs[0]["id"]))


async def test_build_number_held_by_a_run_is_never_taken_over(run_store):
    client = _ok_client()
    with pytest.raises(DataValidationError, match="#4 exists"):
        await _make_service(client, build_id=f"{_NEW_BUILD_ID}#4").ingest(_archive(_run_archive()))

    run_store.reservations.reserve.assert_not_called()
    run_store.reservations.take_over.assert_not_called()


async def test_given_build_number_reserved_by_another_replay_fails(run_store):
    run_store.reservations.reserve.return_value = False
    client = _ok_client()

    with pytest.raises(DataValidationError, match="#7 exists"):
        await _make_service(client, build_id=f"{_NEW_BUILD_ID}#7").ingest(_archive(_run_archive()))
    client.request.assert_not_called()


async def test_dry_run_reserves_no_build_number(run_store):
    await _make_service(build_id=_NEW_BUILD_ID).ingest(_archive(_run_archive()), dry_run=True)

    run_store.reservations.reserve.assert_not_called()


async def test_build_numbers_of_every_plugin_count(run_store):
    other_plugin = MagicMock()
    other_plugin.find.return_value.only.return_value.values_list.return_value.all = AsyncMock(
        return_value=[(12,)])

    with patch.object(ReplayService, "_run_models", return_value=[run_store.model, other_plugin]):
        summary = await _make_service(build_id=_NEW_BUILD_ID).ingest(_archive(_run_archive()))

    # The archive holds an SCT run only, and the path also holds a #12 of another plugin.
    assert summary.runs[0]["build_number"] == 13


@pytest.mark.parametrize("build_id", ["a/b#²", "a/b#٣", "a/b#７"])
async def test_build_number_must_be_ascii_digits(build_id: str):
    with pytest.raises(DataValidationError, match="positive integer"):
        await _make_service(build_id=build_id).ingest(_archive(_run_archive()))


async def test_new_test_takes_no_build_url_of_a_copy(run_store):
    with patch("argus.backend.service.test_hierarchy.ensure_test_hierarchy") as ensure:
        await _make_service(build_id=_NEW_BUILD_ID, create_missing_tests=True).ingest(_archive(_run_archive()))

    assert ensure.call_args.kwargs["build_id"] == _NEW_BUILD_ID
    assert ensure.call_args.kwargs["build_url"] is None


async def test_submit_without_a_run_type_does_not_abort_the_replay(run_store):
    client = _ok_client()
    record = _rec("/testrun/$type/submit", ts=1, location_params={}, body={"run_id": _RUN_ID, "job_name": "x"})
    record["test_type"] = None

    summary = await _make_service(client, build_id=_NEW_BUILD_ID).ingest(_archive([record]))

    assert [e["endpoint"] for e in summary.errors] == ["stamp_run"]
    assert "no run type" in summary.errors[0]["error"]
