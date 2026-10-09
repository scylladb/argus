"""Controller-level tests for :mod:`argus.backend.controller.replay_api`.

Stands up a minimal FastAPI app with only the replay router included so we
don't need the heavyweight Docker/ScyllaDB fixture. The ReplayService is
patched out -- the dispatch logic itself is covered by
``test_replay_service``.
"""
from __future__ import annotations

import io
import json
from datetime import UTC, datetime
import tarfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import zstandard as zstd
from fastapi import FastAPI
from starlette.testclient import TestClient

from argus.backend.controller import replay_api
from argus.backend.error_handlers import APIException, api_exception_handler
from argus.backend.models.web import User
from argus.backend.service.user import load_user
from argus.backend.util.config import Config


@pytest.fixture(autouse=True)
def web_config(monkeypatch):
    monkeypatch.setattr(Config, "CONFIG", {"BASE_URL": "https://argus.example.com"})


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(replay_api.router, prefix="/api/v1/client")
    app.add_exception_handler(APIException, api_exception_handler)
    # No-op the auth pipeline so the test client can hit the endpoint.
    import uuid
    test_user = User(id=uuid.uuid4(), username="replay-test", password="", registration_date=datetime.now(UTC),
                     roles=["ROLE_USER"])
    app.dependency_overrides[load_user] = lambda: test_user
    return app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def _make_archive(records: list[dict]) -> bytes:
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        payload = "\n".join(json.dumps(r) for r in records).encode("utf-8")
        info = tarfile.TarInfo(name="argus_replay_log_r_1.jsonl")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return zstd.ZstdCompressor().compress(tar_buf.getvalue())


def test_replay_ingest_rejects_unsupported_content_type(client):
    response = client.post(
        "/api/v1/client/replay/ingest",
        data=b"...",
        headers={"content-type": "text/plain"},
    )
    # ``handle_api_exception`` returns HTTP 200 with the standard error
    # envelope for every APIException subclass.
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["response"]["exception"] == "UnsupportedMediaType"


def test_replay_ingest_rejects_empty_body(client):
    response = client.post(
        "/api/v1/client/replay/ingest",
        data=b"",
        headers={"content-type": "application/x-tar-zstd"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["response"]["exception"] == "EmptyRequest"


def test_replay_ingest_returns_summary_for_valid_archive(client):
    archive = _make_archive([
        {
            "ts": 1, "method": "POST",
            "endpoint": "/testrun/$type/submit",
            "location_params": {"type": "generic"},
            "params": None,
            "body": {"run_id": "x"},
            "test_type": "generic",
            "success": True,
        }
    ])

    with patch(
        "argus.backend.controller.replay_api.ReplayService"
    ) as mock_service_cls:
        instance = mock_service_cls.return_value
        instance.ingest = AsyncMock(return_value=MagicMock())
        instance.ingest.return_value.as_dict.return_value = {
            "total": 1, "processed": 1, "succeeded": 1, "failed": 0,
            "skipped_no_replay": 0, "errors": [],
        }
        response = client.post(
            "/api/v1/client/replay/ingest",
            content=archive,
            headers={"content-type": "application/x-tar-zstd"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["response"]["total"] == 1
    instance.ingest.assert_called_once()
    _, kwargs = instance.ingest.call_args
    assert kwargs["dry_run"] is False


def test_replay_ingest_dry_run_flag_forwarded(client):
    archive = _make_archive([])
    with patch(
        "argus.backend.controller.replay_api.ReplayService"
    ) as mock_service_cls:
        instance = mock_service_cls.return_value
        instance.ingest = AsyncMock(return_value=MagicMock())
        instance.ingest.return_value.as_dict.return_value = {
            "total": 0, "processed": 0, "succeeded": 0, "failed": 0,
            "skipped_no_replay": 0, "errors": [],
        }
        client.post(
            "/api/v1/client/replay/ingest?dry_run=true",
            content=archive,
            headers={"content-type": "application/x-tar-zstd"},
        )
        _, kwargs = instance.ingest.call_args
        assert kwargs["dry_run"] is True


def test_replay_ingest_forwards_service_error_through_handler(client):
    from argus.backend.service.replay_service import ReplayServiceError
    with patch(
        "argus.backend.controller.replay_api.ReplayService"
    ) as mock_service_cls:
        mock_service_cls.return_value.ingest.side_effect = ReplayServiceError(
            "Failed to decode archive: bad zstd"
        )
        response = client.post(
            "/api/v1/client/replay/ingest",
            content=b"garbage",
            headers={"content-type": "application/x-tar-zstd"},
        )
    # Same handler path as the other validation errors -- 200 + envelope.
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["response"]["exception"] == "ReplayServiceError"
    assert "Failed to decode archive" in response.json()["response"]["message"]


def _service_kwargs(client, query: str) -> dict:
    with patch(
        "argus.backend.controller.replay_api.ReplayService"
    ) as mock_service_cls:
        instance = mock_service_cls.return_value
        instance.ingest = AsyncMock(return_value=MagicMock())
        instance.ingest.return_value.as_dict.return_value = {}
        client.post(
            f"/api/v1/client/replay/ingest{query}",
            content=_make_archive([]),
            headers={"content-type": "application/x-tar-zstd"},
        )
        return mock_service_cls.call_args.kwargs


def test_replay_ingest_passes_the_caller_and_the_flags(client):
    kwargs = _service_kwargs(client, "?build_id=scylla-staging/jdoe/my-run&as_me=false&create_missing_tests=true")

    assert kwargs["build_id"] == "scylla-staging/jdoe/my-run"
    assert kwargs["caller"].username == "replay-test"
    assert kwargs["as_me"] is False
    assert kwargs["create_missing_tests"] is True


def test_replay_ingest_leaves_unset_flags_to_the_service(client):
    kwargs = _service_kwargs(client, "")

    assert kwargs["build_id"] is None
    assert kwargs["caller"].username == "replay-test"
    assert kwargs["as_me"] is None
    assert kwargs["create_missing_tests"] is None
    # A client that sends no local_runs gets the replay it always got.
    assert kwargs["local_runs"] is False


def test_replay_ingest_passes_local_runs_and_the_argus_url(client):
    kwargs = _service_kwargs(client, "?local_runs=true")

    assert kwargs["local_runs"] is True
    assert kwargs["argus_url"] == "https://argus.example.com"


def test_replay_ingest_ignores_the_host_header_without_base_url(client, monkeypatch):
    monkeypatch.setattr(Config, "CONFIG", {"SCYLLA_KEYSPACE_NAME": "argus"})

    kwargs = _service_kwargs(client, "?local_runs=true")

    # A build URL from the request would trust the Host header; the service
    # then stores a relative link.
    assert kwargs["argus_url"] == ""


def test_replay_ingest_forwards_resume_run_id(client):
    kwargs = _service_kwargs(
        client, "?build_id=scylla-staging/jdoe/my-run&resume_run_id=22222222-2222-2222-2222-222222222222")

    assert str(kwargs["resume_run_id"]) == "22222222-2222-2222-2222-222222222222"


def test_replay_ingest_rejects_a_malformed_resume_run_id(client):
    response = client.post(
        "/api/v1/client/replay/ingest?build_id=a/b&resume_run_id=not-a-uuid",
        content=_make_archive([]),
        headers={"content-type": "application/x-tar-zstd"},
    )

    assert response.status_code == 422
