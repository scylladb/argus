"""JSONL replay log for Argus client API calls.

Every mutating (POST) request is recorded as JSONL lines so that, when Argus
is unavailable, the recorded calls can be replayed against the server once it
recovers. See ``docs/plans/request_replay.md`` for the full design.

Each request thread builds a :class:`ReplayRecord`, writes it to disk *before*
making the HTTP call (so a crash mid-call still leaves a record to replay),
runs the call, and writes the record again with the final outcome. The two
writes are distinguished by a ``phase`` field (``"pending"``/``"final"``) so a
replay/ingest tool can tell a not-yet-completed call from its outcome instead
of relying on the shape of ``success``/``error``.

Writes are synchronous, serialized by a single lock -- there is no background
thread or queue, so a failing write can never grow unbounded memory and a slow
disk just adds latency to the calling request instead of losing data silently.
A write or shutdown failure is always logged and swallowed rather than raised:
logging must never be the reason the real Argus API call doesn't happen, and
never the reason a caller's cleanup path raises.
"""
from __future__ import annotations

import atexit
import functools
import itertools
import json
import logging
import os
import re
import threading
import time
import weakref
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import IO, Any, Iterator

_instance_counter = itertools.count()

LOGGER = logging.getLogger(__name__)

# Allow only characters that are unambiguously safe inside a filename.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_-]")


def _sanitize_for_filename(value: str) -> str:
    # Strip any path-significant characters (slashes, dots) so a hostile run-id
    # cannot escape ``log_dir``. Dots are dropped entirely rather than mapped
    # to ``_`` so ``..`` cannot survive the substitution.
    return _UNSAFE_FILENAME_CHARS.sub("_", value) or "unknown"


def _now_ns() -> int:
    return time.time_ns()


@dataclass
class ReplayRecord:
    """One Argus API call. Populated during the HTTP call, written to disk
    both before the call starts (pre-flight) and after it completes/fails."""

    method: str
    endpoint: str
    location_params: dict | None
    params: dict | None
    body: dict | None
    test_type: str
    ts: int = field(default_factory=lambda: _now_ns() // 1_000_000)
    success: bool = False
    error: str | None = None

    def record(self, response: Any) -> None:
        """Populate ``success`` / ``error`` from a ``requests.Response``.

        Only a response with ``response.ok`` true (status < 400) and a JSON
        body with ``status == "ok"`` counts as success. A non-2xx/3xx status,
        a non-JSON body (auth proxy, gateway error), or ``{"status":
        "error", ...}`` is recorded as a failure.
        """
        if not response.ok:
            self.error = f"HTTP {response.status_code}"
            return
        try:
            payload = response.json()
        except ValueError:
            self.error = f"HTTP {response.status_code} non-JSON response"
            return
        if payload.get("status") == "ok":
            self.success = True
        else:
            self.error = f"HTTP {response.status_code} status={payload.get('status')!r}"

    def to_dict(self) -> dict:
        d = asdict(self)
        # Omit ``error`` when there is no error to keep records compact.
        if d["error"] is None:
            del d["error"]
        return d


class ReplayLogOnlyResponse:
    """Stub :class:`requests.Response` returned in replay-log-only mode.

    Satisfies :meth:`ArgusClient.check_response` so callers continue without
    error. The real request is preserved in the replay log for later replay.
    """

    status_code = 200
    ok = True

    def __init__(self, endpoint: str) -> None:
        self.url = f"replay-log-only:{endpoint}"
        self.request = None
        self.text = '{"status":"ok","response":{}}'
        self.content = self.text.encode("utf-8")

    def json(self) -> dict:
        return {"status": "ok", "response": {}}

    def raise_for_status(self) -> None:
        return None


class ReplayLog:
    """Append-only JSONL journal of Argus API calls for one client instance.

    Writes are synchronous and serialized by a single lock -- the calling
    thread pays for its own write, there is no background thread, queue, or
    unbounded buffer that could grow if the disk is unwritable.

    If the log file cannot be opened (bad ``log_dir``, permission error, full
    disk), the instance still constructs successfully and simply drops every
    record -- a broken replay log must never prevent the real Argus client
    from being created or from making its real HTTP calls.
    """

    def __init__(
        self,
        *,
        log_dir: str | Path,
        run_id: str | None = None,
        test_type: str | None = None,
    ) -> None:
        safe_run_id = _sanitize_for_filename(run_id or "unknown")
        log_dir_path = Path(log_dir)
        # Nanosecond clock + pid + process-wide counter guarantees uniqueness
        # across parallel processes and back-to-back instantiation, even when
        # the system clock has coarser-than-nanosecond resolution.
        suffix = f"{_now_ns()}_{os.getpid()}_{next(_instance_counter)}"
        self._path: Path = log_dir_path / f"argus_replay_log_{safe_run_id}_{suffix}.jsonl"
        self._test_type: str = test_type or "unknown"
        self._cv = threading.Condition()
        self._active = 0
        self._closed = False
        self._file: IO[str] | None = None
        try:
            log_dir_path.mkdir(parents=True, exist_ok=True)
            self._file = open(self._path, "a", encoding="utf-8")
        except OSError:
            LOGGER.exception(
                "argus replay log: could not open %s for writing; replay log disabled", self._path,
            )
        self._atexit_ref: weakref.ReferenceType[ReplayLog] = weakref.ref(self)
        self._atexit_callback = functools.partial(self._atexit_close, self._atexit_ref)
        atexit.register(self._atexit_callback)

    @staticmethod
    def _atexit_close(log_ref: "weakref.ReferenceType[ReplayLog]") -> None:
        log = log_ref()
        if log is not None:
            log.close()

    @property
    def path(self) -> Path:
        return self._path

    def __enter__(self) -> "ReplayLog":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def _line(item: dict) -> str:
        # Compact separators (no spaces) -- ~10-15% smaller than the default.
        return json.dumps(item, default=str, separators=(",", ":"), ensure_ascii=False) + "\n"

    def _write(self, rec: ReplayRecord, *, phase: str) -> None:
        try:
            # `rec.to_dict()` (dataclasses.asdict) walks the whole
            # method/endpoint/params/body structure and can itself raise
            # (e.g. RecursionError on a circular body) -- so it must be
            # inside this same guard, not just the json.dumps() below.
            item = rec.to_dict()
            item["phase"] = phase
            line = self._line(item)
        except Exception:
            # Serialization must never take down the caller's request; drop
            # this one record rather than raise out of record().
            LOGGER.exception("argus replay log: failed to serialize record; record dropped")
            return
        with self._cv:
            if self._file is None:
                # Already logged loudly once, in __init__, when the file
                # failed to open -- avoid re-warning on every record.
                LOGGER.debug(
                    "argus replay log: log unavailable; dropping %s record for %s %s",
                    phase, item.get("method"), item.get("endpoint"),
                )
                return
            if self._file.closed:
                LOGGER.warning(
                    "argus replay log: log already closed; dropping %s record for %s %s",
                    phase, item.get("method"), item.get("endpoint"),
                )
                return
            try:
                # write + flush only: fsync/fdatasync was measured (100
                # concurrent threads) to add no durability benefit here and
                # cost real latency on every request -- see PR discussion.
                self._file.write(line)
                self._file.flush()
            except Exception:
                # A write failure must never propagate into the caller's
                # request handling; the record for this one call is lost,
                # but nothing here can leak memory since there is no queue.
                LOGGER.exception("argus replay log: write failed; record dropped")

    @contextmanager
    def record(
        self,
        method: str,
        endpoint: str,
        location_params: dict | None,
        params: dict | None,
        body: dict | None,
    ) -> Iterator[ReplayRecord]:
        """Yield a :class:`ReplayRecord` for the caller to populate.

        The record is written to disk immediately, before the caller's HTTP
        call runs, so a crash/SIGKILL mid-call still leaves a (pending)
        record to replay. The caller runs the HTTP call inside the ``with``
        block and sets ``rec.success`` based on the response; if the block
        raises, ``success`` stays ``False`` and ``error`` captures the
        exception. The record is written again with the final outcome on
        exit either way.

        If the log has already been closed, the request is not recorded at
        all -- but it still runs normally; a closed/broken replay log must
        never block or fail the caller's real HTTP call.
        """
        with self._cv:
            active = not self._closed
            if active:
                self._active += 1

        try:
            rec = ReplayRecord(
                method=method,
                endpoint=endpoint,
                location_params=location_params,
                params=params,
                body=body,
                test_type=self._test_type,
            )
            if active:
                self._write(rec, phase="pending")
            try:
                yield rec
            except Exception as exc:
                rec.success = False
                rec.error = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                if active:
                    self._write(rec, phase="final")
        finally:
            # However the block above exits (including a failure before the
            # first write ever happens), the in-flight count must drop so a
            # concurrent close() does not wait forever.
            if active:
                with self._cv:
                    self._active -= 1
                    if self._active == 0:
                        self._cv.notify_all()

    def close(self, timeout: float = 5.0) -> None:
        with self._cv:
            if self._closed:
                return
            self._closed = True
            # Let any record() call that started before close() finish
            # writing its final entry -- otherwise a request already
            # in-flight would silently lose its log entry.
            if not self._cv.wait_for(lambda: self._active == 0, timeout=timeout):
                LOGGER.warning(
                    "argus replay log: closing with %d in-flight record(s) still pending",
                    self._active,
                )
            if self._file is not None:
                try:
                    self._file.close()
                except OSError:
                    LOGGER.exception("argus replay log: error closing %s", self._path)
        atexit.unregister(self._atexit_callback)
