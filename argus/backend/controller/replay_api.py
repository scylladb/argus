"""Replay-log ingest endpoint.

POST /api/v1/client/replay/ingest

Accepts an archive of JSONL replay logs and re-applies the recorded
requests against the running Flask app (via an in-process proxy through
``current_app.test_client()``). See ``docs/plans/request_replay.md`` for
the full design.

Supported archive formats: ``tar.zst`` (the canonical CLI output),
``tar.gz``/``tgz``, plain ``tar``, and ``zip``. Format is detected from
magic bytes in the request body; the ``Content-Type`` header is only
used to reject obvious mismatches at the door.
"""
from __future__ import annotations

from flask import Blueprint, request

from argus.backend.error_handlers import APIException, handle_api_exception
from argus.backend.service.replay_service import ReplayService
from argus.backend.service.user import api_login_required

bp = Blueprint("replay_api", __name__, url_prefix="/replay")
bp.register_error_handler(Exception, handle_api_exception)


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

    return {"status": "ok", "response": summary.as_dict()}
