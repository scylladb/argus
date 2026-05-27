"""Server-side replay-log ingest.

Receives a ``tar.zst`` archive of JSONL replay-log records (produced by the
Argus Python client) and re-applies each recorded request against the running
Flask app.

Design: we deliberately do **not** reimplement the controller logic
endpoint-by-endpoint. Each record carries enough information --
``endpoint`` template, ``location_params`` for ``$placeholder`` substitution,
optional ``params`` query string, ``method``, and JSON ``body`` -- to
reconstruct the original HTTP call. We send that reconstructed call through
Flask's in-process :py:meth:`~flask.Flask.test_client`, so the real
controller, decorators (auth, error handling) and idempotency logic kick in
exactly as they would for a live client.

Two side concerns remain server-side:

* **Ordering** -- ``submit_run`` must run before anything referencing the run,
  terminal ``set_status`` runs last so ``end_time`` is back-filled, and
  heartbeats collapse to the most recent record (per run).
* **Skip-list** -- endpoints with side effects outside Argus
  (``/testrun/report/email``, ``/planning/plan/trigger``) and the legacy
  batch ``/sct/$id/events/submit`` are skipped: replaying them would send
  emails, trigger jobs, or duplicate event rows.

When ``create_missing_tests`` is set, ``submit_run`` records get a pre-step
that ensures the ``ArgusRelease/Group/Test`` triple exists for the run's
build_id, so that the controller's ``assign_categories`` can populate
``test_id`` on the row. This is opt-in because curated instances already have
the hierarchy populated and don't want orphan auto-creates.
"""
import io
import json
import logging
import re
import tarfile
from dataclasses import dataclass, field
from typing import Iterable

import zstandard as zstd
from flask import current_app

from argus.backend.error_handlers import APIException

LOGGER = logging.getLogger(__name__)

# Endpoint templates whose dispatch we never want to perform during replay.
# These either touch systems outside Argus (email, CI) or are superseded
# by other endpoints in the same log (the legacy bulk events submit).
SKIP_ENDPOINTS: frozenset[str] = frozenset({
    "/testrun/report/email",       # would send actual mail
    "/planning/plan/trigger",      # would re-trigger CI jobs
    # Legacy bulk submit -- the individual ``/sct/$id/event/submit`` records
    # in the same log already carry the same data and replaying both would
    # duplicate rows.
    "/sct/$id/events/submit",
    # ``finalize`` is folded into terminal ``set_status`` by the new client
    # flow; older logs that still emit it are no-ops.
    "/testrun/$type/$id/finalize",
})

# Set of ``set_status`` body.new_status values that we treat as terminal.
TERMINAL_STATUSES = frozenset({
    "failed", "aborted", "passed", "error", "notrun", "not_run",
})

# Routes recorded by the client live under this prefix on the server. The
# replay-log endpoint templates are blueprint-relative (e.g.
# ``/testrun/$type/submit``); we prepend this when reconstructing the URL
# for the Flask test client.
CLIENT_ROUTE_PREFIX = "/api/v1/client"


@dataclass
class ReplayOutcome:
    ts: int
    endpoint: str
    status: str  # "ok", "error", "skipped"
    error: str | None = None


@dataclass
class ReplaySummary:
    total: int = 0
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped_no_replay: int = 0
    errors: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "processed": self.processed,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped_no_replay": self.skipped_no_replay,
            "errors": self.errors,
        }


class ReplayServiceError(APIException):
    """Raised when the replay archive itself cannot be processed.

    Inherits from :class:`APIException` so the registered error handler on
    the ingest blueprint converts it into the standard error envelope
    instead of letting the controller marshal it by hand.
    """


class ReplayService:
    """Replay one ``tar.zst`` archive against the current Flask app."""

    # The Werkzeug test client returns wrapped responses; the body is
    # available via ``get_data(as_text=True)``. We cap the body slice we
    # include in error reports to keep summaries from ballooning.
    _ERROR_BODY_MAX = 400

    def __init__(
        self,
        *,
        app=None,
        auth_header: str | None = None,
        create_missing_tests: bool = False,
    ) -> None:
        self._app = app
        self._auth_header = auth_header
        self._create_missing_tests = create_missing_tests

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def ingest(self, archive_bytes: bytes, *, dry_run: bool = False) -> ReplaySummary:
        records = list(self._extract_records(archive_bytes))
        records = self._apply_ordering(records)

        summary = ReplaySummary(total=len(records))
        if not records:
            return summary

        client = self._test_client()
        for rec in records:
            self._process_one(client, rec, summary, dry_run=dry_run)
        return summary

    def _test_client(self):
        """Resolve the Flask test client to dispatch through.

        Prefers an explicitly-injected app (used by unit tests); falls back
        to :py:obj:`flask.current_app` so the controller doesn't need to
        thread the app through.
        """
        app = self._app or current_app._get_current_object()  # type: ignore[attr-defined]
        return app.test_client()

    # ------------------------------------------------------------------
    # Archive handling
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_records(archive_bytes: bytes) -> Iterable[dict]:
        """Yield records from every JSONL file in the archive.

        Streams the decompressed bytes through ``tarfile`` so we never
        materialize the full uncompressed archive at once. Skips non-JSONL
        members and bad lines (with a warning) rather than aborting -- a
        single corrupt line should not invalidate the whole replay.
        """
        decompressor = zstd.ZstdDecompressor()
        try:
            with decompressor.stream_reader(io.BytesIO(archive_bytes)) as stream:
                with tarfile.open(fileobj=stream, mode="r|") as tar:
                    for member in tar:
                        if not member.isfile() or not member.name.endswith(".jsonl"):
                            continue
                        fobj = tar.extractfile(member)
                        if fobj is None:
                            continue
                        for line_no, raw in enumerate(fobj, 1):
                            line = raw.strip()
                            if not line:
                                continue
                            try:
                                yield json.loads(line)
                            except json.JSONDecodeError as exc:
                                LOGGER.warning(
                                    "Skipping malformed line in %s:%d (%s)",
                                    member.name, line_no, exc,
                                )
        except (zstd.ZstdError, tarfile.TarError) as exc:
            raise ReplayServiceError(f"Failed to decode archive: {exc}") from exc

    # ------------------------------------------------------------------
    # Endpoint normalisation
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_endpoint(endpoint: str) -> str:
        """Collapse repeated slashes in ``endpoint``.

        Earlier versions of the SCT client emitted
        ``/sct/$id//stress_cmd/submit`` (note the double slash) due to a
        route-constant typo. Logs recorded by those clients are still in the
        wild, so we normalise on read instead of letting them mismatch on
        dispatch.
        """
        if "//" not in endpoint:
            return endpoint
        if "://" in endpoint:
            scheme, _, rest = endpoint.partition("://")
            return f"{scheme}://{re.sub(r'/{2,}', '/', rest)}"
        return re.sub(r"/{2,}", "/", endpoint)

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_ordering(records: list[dict]) -> list[dict]:
        """Sort by ``ts``, then enforce the plan's invariants:

        * ``submit_run`` records run first (the run must exist before
          anything else touches it).
        * Terminal ``set_status`` records run last (back-fills ``end_time``).
        * Heartbeats are collapsed to only the last one per ``(type, id)``.
        """
        records.sort(key=lambda r: r.get("ts", 0))

        submit_runs: list[dict] = []
        terminal_statuses: list[dict] = []
        middle: list[dict] = []
        last_heartbeat: dict[tuple, dict] = {}

        for r in records:
            endpoint = ReplayService._normalise_endpoint(r.get("endpoint", ""))
            if endpoint == "/testrun/$type/submit":
                submit_runs.append(r)
            elif endpoint == "/testrun/$type/$id/set_status" and ReplayService._is_terminal_status(r):
                terminal_statuses.append(r)
            elif endpoint == "/testrun/$type/$id/heartbeat":
                loc = r.get("location_params") or {}
                key = (loc.get("type"), loc.get("id"))
                last_heartbeat[key] = r
            else:
                middle.append(r)

        return submit_runs + middle + list(last_heartbeat.values()) + terminal_statuses

    @staticmethod
    def _is_terminal_status(record: dict) -> bool:
        body = record.get("body") or {}
        new_status = (body.get("new_status") or "").lower()
        return new_status in TERMINAL_STATUSES

    # ------------------------------------------------------------------
    # URL reconstruction
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_url(endpoint_template: str, location_params: dict) -> str:
        """Substitute ``$name`` placeholders in ``endpoint_template``.

        Returns the full Flask URL (with the ``/api/v1/client`` prefix the
        recorded templates are relative to).
        """
        url = endpoint_template
        for key, value in (location_params or {}).items():
            url = url.replace(f"${key}", str(value))
        return CLIENT_ROUTE_PREFIX + url

    # ------------------------------------------------------------------
    # Hierarchy auto-create (pre-step for submit_run)
    # ------------------------------------------------------------------
    @staticmethod
    def _ensure_hierarchy_for_submit_run(record: dict) -> None:
        """Auto-create the ``ArgusRelease/Group/Test`` triple referenced by a
        ``submit_run`` record's build identifier and, if a run row already
        exists for this ``run_id`` with empty categorical fields, back-fill
        them so subsequent ``submit_results`` calls (partitioned by
        ``test_id``) succeed.

        Only invoked when ``create_missing_tests`` is set. No-ops silently
        when the body lacks a recognisable build identifier; the controller
        will then fail with its own error.
        """
        body = record.get("body") or {}
        location = record.get("location_params") or {}
        run_type = location.get("type", "")

        build_id = body.get("job_name") or body.get("build_id") or body.get("buildId")
        if not build_id:
            LOGGER.debug(
                "No build_id in submit_run body for run_type=%s; skipping hierarchy auto-create",
                run_type,
            )
            return

        build_url = body.get("job_url") or body.get("build_job_url")
        run_id = body.get("run_id")

        # Lazy imports: avoid circulars and keep this off the import-time
        # critical path of normal request handling.
        from argus.backend.service.test_hierarchy import ensure_test_hierarchy
        from argus.backend.service.client_service import ClientService

        test = ensure_test_hierarchy(
            build_id=build_id,
            build_url=build_url,
            plugin_name=run_type or None,
        )

        if not run_id:
            return
        try:
            model = ClientService().get_model(run_type)
            from uuid import UUID
            run = model.get(id=UUID(run_id))
        except Exception:  # noqa: BLE001 -- DoesNotExist or unknown run_type
            return

        changed = False
        if not getattr(run, "test_id", None):
            run.test_id = test.id
            changed = True
        if not getattr(run, "release_id", None):
            run.release_id = test.release_id
            changed = True
        if not getattr(run, "group_id", None):
            run.group_id = test.group_id
            changed = True
        if changed:
            run.save()
            LOGGER.info(
                "Back-filled categorical fields on existing run %s (test_id=%s)",
                run_id, test.id,
            )

    # ------------------------------------------------------------------
    # Per-record execution
    # ------------------------------------------------------------------
    def _process_one(
        self,
        client,
        record: dict,
        summary: ReplaySummary,
        *,
        dry_run: bool,
    ) -> None:
        endpoint = self._normalise_endpoint(record.get("endpoint", ""))
        ts = record.get("ts", 0)

        if endpoint in SKIP_ENDPOINTS:
            summary.skipped_no_replay += 1
            return

        if dry_run:
            summary.processed += 1
            summary.succeeded += 1
            return

        # Pre-step: ensure the Release/Group/Test hierarchy exists for the
        # build_id referenced by submit_run, when opted in. Done before
        # dispatch so ``assign_categories`` can resolve ``test_id`` on the
        # initial insert. Failures here are non-fatal -- we still try the
        # dispatch and surface its error.
        if self._create_missing_tests and endpoint == "/testrun/$type/submit":
            try:
                self._ensure_hierarchy_for_submit_run(record)
            except Exception:  # noqa: BLE001
                LOGGER.exception(
                    "Hierarchy auto-create failed for ts=%s; continuing with dispatch", ts,
                )

        location_params = record.get("location_params") or {}
        params = record.get("params") or {}
        body = record.get("body")
        method = (record.get("method") or "POST").upper()

        url = self._resolve_url(endpoint, location_params)

        headers = {}
        if self._auth_header:
            headers["Authorization"] = self._auth_header

        try:
            response = client.open(
                url,
                method=method,
                query_string=params or None,
                json=body if body is not None else None,
                headers=headers,
            )
        except Exception as exc:  # noqa: BLE001 -- isolate per-record
            summary.processed += 1
            summary.failed += 1
            summary.errors.append({
                "ts": ts,
                "endpoint": endpoint,
                "error": f"{type(exc).__name__}: {exc}",
            })
            LOGGER.exception(
                "Replay raised dispatching ts=%s endpoint=%s url=%s",
                ts, endpoint, url,
            )
            return

        summary.processed += 1
        status = response.status_code
        if 200 <= status < 300:
            # Some controllers wrap errors in a 200 envelope with
            # ``{"status": "error", ...}``. Treat that as a failure so the
            # caller sees what really happened.
            envelope_error = self._envelope_error(response)
            if envelope_error is not None:
                summary.failed += 1
                summary.errors.append({
                    "ts": ts,
                    "endpoint": endpoint,
                    "error": envelope_error[: self._ERROR_BODY_MAX],
                })
                return
            summary.succeeded += 1
            return

        body_text = response.get_data(as_text=True)
        summary.failed += 1
        summary.errors.append({
            "ts": ts,
            "endpoint": endpoint,
            "error": f"HTTP {status}: {body_text[: self._ERROR_BODY_MAX]}",
        })

    @staticmethod
    def _envelope_error(response) -> str | None:
        """If a 2xx response carries the standard ``{"status": "error"}``
        envelope, return a one-line description; otherwise return None.
        """
        try:
            data = response.get_json(silent=True)
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(data, dict):
            return None
        if data.get("status") != "error":
            return None
        resp = data.get("response") or {}
        exc = resp.get("exception") or ""
        args = resp.get("arguments") or []
        msg = data.get("message") or ""
        if exc and args:
            return f"{exc}: {args}"
        if exc:
            return exc
        if msg:
            return msg
        return json.dumps(data)
