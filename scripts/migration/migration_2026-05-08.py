import json
import logging
import os
import re
from datetime import datetime, UTC
from pathlib import Path
from uuid import UUID

from cassandra import InvalidRequest
from cassandra.query import SimpleStatement
from coodie.sync import BatchQuery

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTEvent, SCTEventSeverity, SCTTestRun
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()

PAGE_SIZE = 200
READ_TIMEOUT = 120.0
# Split budget for a run's batches. Scylla warns at batch_size_warn_threshold_in_kb
# (128 KB default) and rejects at batch_size_fail_threshold_in_kb (1024 KB default).
MAX_BATCH_BYTES = 64 * 1024
STATE_FILE = Path(os.environ.get("ARGUS_MIGRATION_STATE", "/var/tmp/argus-migration-2026-05-08.state"))

EVENT_REGEX = re.compile(
    r"(?P<eventTimestamp>\d{2,4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})"
    r"( <(?P<receiveTimestamp>\d{2,4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})>)?"
    r": \((?P<eventType>\w+) Severity\.(?P<severity>[A-Z]+)\) (?P<rawFields>.+)",
    re.DOTALL,
)


def parse_event_fields(raw_fields: str) -> dict[str, str]:
    """Port of frontend parseEventFields: splits 'key=value key=value ...' respecting spaces in values."""
    pos = 0
    split_points = [0]
    potential_split = False
    potential_split_pos = 0

    for pos, ch in enumerate(raw_fields):
        if ch == " ":
            potential_split = True
            potential_split_pos = pos + 1
        elif potential_split and ch == "=":
            split_points.append(potential_split_pos)
            potential_split = False

    parsed = {}
    for i, start in enumerate(split_points):
        end = split_points[i + 1] if i + 1 < len(split_points) else len(raw_fields)
        fragment = raw_fields[start:end]
        parts = fragment.split("=", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            continue
        parsed[parts[0].strip()] = parts[1].strip().rstrip(",:")

    return parsed


def parse_timestamp(ts_str: str) -> datetime | None:
    """Parse event timestamp string into a datetime."""
    if not ts_str:
        return None
    try:
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_event_message(message: str) -> dict:
    """Parse a legacy event message string into structured fields."""
    newline_idx = message.find("\n")
    if newline_idx == -1:
        meta = message
    else:
        meta = message[:newline_idx]

    match = EVENT_REGEX.match(meta)
    if not match:
        return {"message": message}

    groups = match.groupdict()
    fields = parse_event_fields(groups.get("rawFields", "").strip())

    result = {
        "event_type": groups.get("eventType"),
        "ts": parse_timestamp(groups.get("eventTimestamp")),
        "message": message,
        "received_timestamp": parse_timestamp(groups.get("receiveTimestamp")),
        "node": fields.get("node"),
        "target_node": fields.get("target_node"),
        "known_issue": fields.get("known_issue"),
        "nemesis_name": fields.get("nemesis_name"),
        "duration": None,
        "nemesis_status": fields.get("nemesis_status"),
    }

    duration_raw = fields.get("duration")
    if duration_raw:
        try:
            result["duration"] = float(duration_raw)
        except ValueError:
            pass

    return result


def run_has_events(run_id) -> bool:
    """Check if the run already has events in the SCTEvent table."""
    results = (
        SCTEvent.find(
            run_id=run_id,
            severity__in=[s.value for s in SCTEventSeverity],
        )
        .limit(1)
        .all()
    )
    return len(list(results)) > 0


def read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    raw = STATE_FILE.read_text().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        LOGGER.warning("Ignoring unreadable state file %s", STATE_FILE)
        return {}


def set_paging_state(paging_state: bytes | None) -> None:
    state = read_state()
    state["paging_state"] = paging_state.hex() if paging_state else None
    state["in_flight_run_id"] = None
    STATE_FILE.write_text(json.dumps(state))


def set_in_flight(run_id) -> None:
    state = read_state()
    state["in_flight_run_id"] = str(run_id) if run_id else None
    STATE_FILE.write_text(json.dumps(state))


def purge_run_events(run_id) -> None:
    """Delete a run's SCTEvent rows across every severity partition."""
    for severity in SCTEventSeverity:
        SCTEvent.find(run_id=run_id, severity=severity.value).delete()


def recover_interrupted_run() -> None:
    """Drop the partial writes of a run interrupted by an earlier invocation.

    The run is re-read on the redone page, so purging leaves it unmigrated and
    the scan picks it up again.
    """
    raw_run_id = read_state().get("in_flight_run_id")
    if not raw_run_id:
        return
    run_id = UUID(raw_run_id)
    LOGGER.warning("Purging partial events left by interrupted run_id=%s", run_id)
    purge_run_events(run_id)
    set_in_flight(None)


def iter_run_pages():
    """Yield pages of (id, events) rows, saving the paging state after each one."""
    statement = SimpleStatement(f"SELECT id, events FROM {SCTTestRun.table_name()}", fetch_size=PAGE_SIZE)
    raw_paging_state = read_state().get("paging_state")
    paging_state = bytes.fromhex(raw_paging_state) if raw_paging_state else None
    if paging_state:
        LOGGER.warning("Resuming scan from the paging state saved in %s", STATE_FILE)
    while True:
        result = DB.session.execute(
            statement,
            paging_state=paging_state,
            execution_profile="read_fast",
            timeout=READ_TIMEOUT,
        )
        yield result.current_rows
        paging_state = result.paging_state
        set_paging_state(paging_state)
        if paging_state is None:
            return


def build_chunks(run_id, events) -> tuple[list[tuple[list[SCTEvent], int]], int, int]:
    """Group a run's legacy events into byte-budgeted chunks, in order.

    Returns the chunks as (events, byte size) along with the run's total event
    count and parse failures.
    """
    chunks: list[tuple[list[SCTEvent], int]] = []
    total_events = 0
    parse_failures = 0
    fallback_ts = datetime.now(tz=UTC)

    chunk: list[SCTEvent] = []
    chunk_bytes = 0

    for event_group in events:
        severity = event_group.severity
        for message in event_group.last_events:
            message_bytes = len(message.encode("utf-8"))
            if chunk and chunk_bytes + message_bytes > MAX_BATCH_BYTES:
                chunks.append((chunk, chunk_bytes))
                chunk = []
                chunk_bytes = 0
            if message_bytes > MAX_BATCH_BYTES:
                LOGGER.warning(
                    "Event over the %d budget for run_id=%s: %d bytes, writing it as a single insert",
                    MAX_BATCH_BYTES,
                    run_id,
                    message_bytes,
                )

            parsed = parse_event_message(message)
            chunk.append(
                SCTEvent(
                    run_id=run_id,
                    severity=severity,
                    ts=parsed.get("ts") or fallback_ts,
                    event_type=parsed.get("event_type"),
                    message=parsed["message"],
                    received_timestamp=parsed.get("received_timestamp"),
                    node=parsed.get("node"),
                    target_node=parsed.get("target_node"),
                    known_issue=parsed.get("known_issue"),
                    nemesis_name=parsed.get("nemesis_name"),
                    duration=parsed.get("duration"),
                    nemesis_status=parsed.get("nemesis_status"),
                )
            )
            if parsed.get("ts") is None:
                parse_failures += 1
            total_events += 1
            chunk_bytes += message_bytes

    if chunk:
        chunks.append((chunk, chunk_bytes))

    return chunks, total_events, parse_failures


def execute_chunk(chunk: list[SCTEvent]) -> None:
    """Write a chunk; a lone event goes out as a plain insert rather than a batch."""
    if len(chunk) == 1:
        chunk[0].save()
        return

    batch = BatchQuery()
    for event in chunk:
        event.save(batch=batch)
    batch.execute()


def migrate_run(run_id, events) -> tuple[int, int, str | None]:
    """Write one run's legacy events as serially executed chunks.

    Returns (events written, parse failures, failure reason). A rejected chunk
    aborts the run and its partial writes are purged, so a later pass retries it.
    """
    chunks, total_events, parse_failures = build_chunks(run_id, events)
    if not chunks:
        return 0, 0, None

    set_in_flight(run_id)
    written = 0
    for index, (chunk, chunk_bytes) in enumerate(chunks, start=1):
        try:
            execute_chunk(chunk)
        except InvalidRequest:
            LOGGER.error(
                "InvalidRequest executing chunk %d/%d: run_id=%s events=%d bytes=%d written=%d/%d",
                index,
                len(chunks),
                run_id,
                len(chunk),
                chunk_bytes,
                written,
                total_events,
            )
            purge_run_events(run_id)
            set_in_flight(None)
            return 0, 0, f"chunk {index}/{len(chunks)} rejected ({len(chunk)} events, {chunk_bytes} bytes)"
        written += len(chunk)

    set_in_flight(None)
    return written, parse_failures, None


def migrate():
    LOGGER.warning("Starting migration: copying events from SCTTestRun.events into SCTEvent table...")
    recover_interrupted_run()

    total_runs = 0
    skipped_runs = 0
    total_events = 0
    parse_failures = 0
    failed_runs: list[tuple[str, str]] = []

    for page in iter_run_pages():
        for row in page:
            total_runs += 1
            run_id = row["id"]
            events = row["events"]
            if not events:
                skipped_runs += 1
                continue

            if run_has_events(run_id):
                LOGGER.info("Skipping run_id=%s: already has events in SCTEvent table", run_id)
                skipped_runs += 1
                continue

            run_event_count, run_parse_failures, failure = migrate_run(run_id, events)
            if failure:
                failed_runs.append((str(run_id), failure))
                continue

            total_events += run_event_count
            parse_failures += run_parse_failures
            LOGGER.info(
                "Migrated %d events for run_id=%s",
                run_event_count,
                run_id,
            )

    STATE_FILE.unlink(missing_ok=True)
    LOGGER.warning(
        "Migration complete. runs_processed=%d skipped=%d events_migrated=%d parse_failures=%d failed=%d",
        total_runs,
        skipped_runs,
        total_events,
        parse_failures,
        len(failed_runs),
    )
    if failed_runs:
        LOGGER.error("The following %d runs were left unmigrated:", len(failed_runs))
        for run_id, reason in failed_runs:
            LOGGER.error("  run_id=%s %s", run_id, reason)


if __name__ == "__main__":
    migrate()
