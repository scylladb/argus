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
from unittest.mock import patch

import pytest
import zstandard as zstd
from fastapi import FastAPI
from starlette.testclient import TestClient

from argus.backend.controller import replay_api
from argus.backend.error_handlers import APIException, api_exception_handler
from argus.backend.models.web import User
from argus.backend.service.user import load_user


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
