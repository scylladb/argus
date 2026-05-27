"""Replay-log ingest endpoint.

POST /api/v1/client/replay/ingest

Accepts a ``tar.zst`` archive of JSONL replay logs and re-applies the
recorded requests against the running Flask app (via an in-process proxy
through ``current_app.test_client()``). See ``docs/plans/request_replay.md``
for the full design.
"""
from __future__ import annotations

import logging

from flask import Blueprint, request

from argus.backend.error_handlers import APIException, handle_api_exception
from argus.backend.service.replay_service import ReplayService
from argus.backend.service.user import api_login_required

LOGGER = logging.getLogger(__name__)

bp = Blueprint("replay_api", __name__, url_prefix="/replay")
bp.register_error_handler(Exception, handle_api_exception)


ACCEPTED_CONTENT_TYPES = frozenset({
    "application/x-tar-zstd",
    "application/zstd",
    "application/octet-stream",
})


class UnsupportedMediaType(APIException):
    """Request body is not one of :data:`ACCEPTED_CONTENT_TYPES`."""


class EmptyRequest(APIException):
    """Request body is empty -- nothing to ingest."""


@bp.route("/ingest", methods=["POST"])
@api_login_required
def replay_ingest():
    content_type = (request.content_type or "").split(";", 1)[0].strip().lower()
    if content_type and content_type not in ACCEPTED_CONTENT_TYPES:
        raise UnsupportedMediaType(
            f"expected one of {sorted(ACCEPTED_CONTENT_TYPES)}, got {content_type!r}"
        )

    archive = request.get_data(cache=False)
    if not archive:
        raise EmptyRequest("request body is empty")

    dry_run = request.args.get("dry_run", "false").lower() in {"1", "true", "yes"}
    create_missing_tests = request.args.get(
        "create_missing_tests", "false",
    ).lower() in {"1", "true", "yes"}

    # Propagate the caller's Authorization header to the in-process
    # ``test_client`` so internal proxied requests inherit the same identity
    # the controllers would otherwise reject.
    auth_header = request.headers.get("Authorization")

    # ``ReplayServiceError`` inherits from ``APIException`` and is handled
    # by the blueprint's error handler registered above.
    summary = ReplayService(
        auth_header=auth_header,
        create_missing_tests=create_missing_tests,
    ).ingest(archive, dry_run=dry_run)

    LOGGER.info(
        "Replay ingest complete: total=%d processed=%d ok=%d failed=%d skipped=%d "
        "(dry_run=%s, create_missing_tests=%s)",
        summary.total, summary.processed, summary.succeeded,
        summary.failed, summary.skipped_no_replay, dry_run, create_missing_tests,
    )
    return {"status": "ok", "response": summary.as_dict()}
