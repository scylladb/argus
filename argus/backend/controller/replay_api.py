"""Replay-log ingest endpoint.

POST /api/v1/client/replay/ingest

Accepts an archive of JSONL replay logs and re-applies the recorded
requests against the running application (via an in-process TestClient
over the ASGI app). See ``docs/plans/request_replay.md`` for the full
design.

Supported archive formats: ``tar.zst`` (the canonical CLI output),
``tar.gz``/``tgz``, plain ``tar``, and ``zip``. Format is detected from
magic bytes in the request body; the ``Content-Type`` header is only
used to reject obvious mismatches at the door.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query, Request
from flask import Blueprint

from argus.backend.error_handlers import APIException
from argus.backend.models.web import User
from argus.backend.service.replay_service import ReplayService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import ArgusJSONResponse

router = APIRouter(prefix="/replay")

ACCEPTED_CONTENT_TYPES = frozenset({
    # tar.zst -- canonical CLI output
    "application/x-tar-zstd",
    "application/zstd",
    # tar.gz / .tgz / raw .gz
    "application/gzip",
    "application/x-gzip",
    "application/x-tar-gzip",
    "application/x-tgz",
    # plain tar
    "application/x-tar",
    "application/tar",
    # zip
    "application/zip",
    "application/x-zip-compressed",
    "application/x-zip",
    # generic binary upload (curl default)
    "application/octet-stream",
})


class UnsupportedMediaType(APIException):
    """Request body is not one of :data:`ACCEPTED_CONTENT_TYPES`."""


class EmptyRequest(APIException):
    """Request body is empty -- nothing to ingest."""


@router.post("/ingest", name="api.client_api.replay_api.replay_ingest")
def replay_ingest(asgi_request: Request, archive: bytes = Body(b""),
                  dry_run: bool = Query(False),
                  create_missing_tests: bool = Query(False),
                  backfill_logs: bool = Query(True),
                  user: User = Depends(api_current_user)):
    content_type = (asgi_request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if content_type and content_type not in ACCEPTED_CONTENT_TYPES:
        raise UnsupportedMediaType(
            f"expected one of {sorted(ACCEPTED_CONTENT_TYPES)}, got {content_type!r}"
        )

    if not archive:
        raise EmptyRequest("request body is empty")

    # Propagate the caller's Authorization header to the in-process
    # TestClient so internal proxied requests inherit the same identity
    # the controllers would otherwise reject.
    auth_header = asgi_request.headers.get("Authorization")

    service = ReplayService(
        app=asgi_request.app,
        auth_header=auth_header,
        create_missing_tests=create_missing_tests,
        backfill_logs=backfill_logs,
    )
    summary = service.ingest(archive, dry_run=dry_run)

    return ArgusJSONResponse({
        "status": "ok",
        "response": summary.as_dict(),
    })


# The route above is served by FastAPI; this view-less rule keeps the
# endpoint buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint("replay_api", __name__, url_prefix="/replay")
bp.add_url_rule("/ingest", "replay_ingest", None)
