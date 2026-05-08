import logging
import re
from datetime import datetime, UTC

from cassandra import InvalidRequest
from cassandra.cqlengine.query import BatchQuery

from argus.backend.db import ScyllaCluster
from argus.backend.plugins.sct.testrun import SCTEvent, SCTEventSeverity, SCTTestRun
from argus.backend.util.logsetup import setup_application_logging


setup_application_logging(log_level=logging.INFO)
LOGGER = logging.getLogger(__name__)
DB = ScyllaCluster.get()
# 512 KiB, well under Cassandra's default 1 MiB batch size warn threshold
MAX_BATCH_BYTES = 512 * 1024

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
        SCTEvent.filter(
            run_id=run_id,
            severity__in=[s.value for s in SCTEventSeverity],
        )
        .limit(1)
        .all()
    )
    return len(list(results)) > 0


def migrate():
    LOGGER.warning("Starting migration: copying events from SCTTestRun.events into SCTEvent table...")

    total_runs = 0
    skipped_runs = 0
    total_events = 0
    parse_failures = 0

    for run in SCTTestRun.filter().limit(None).only(["id", "events"]).all():
        total_runs += 1
        events = run.events
        if not events:
            skipped_runs += 1
            continue

        if run_has_events(run.id):
            LOGGER.info("Skipping run_id=%s: already has events in SCTEvent table", run.id)
            skipped_runs += 1
            continue

        run_event_count = 0
        batch_count = 0
        batch_bytes = 0
        fallback_ts = datetime.now(tz=UTC)
        b = BatchQuery()
        for event_group in events:
            severity = event_group.severity
            for message in event_group.last_events:
                parsed = parse_event_message(message)
                event_ts = parsed.get("ts") or fallback_ts
                SCTEvent.batch(b).create(
                    run_id=run.id,
                    severity=severity,
                    ts=event_ts,
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
                if parsed.get("ts") is None:
                    parse_failures += 1
                run_event_count += 1
                batch_count += 1
                batch_bytes += len(message.encode("utf-8"))
                if batch_bytes >= MAX_BATCH_BYTES:
                    try:
                        b.execute()
                    except InvalidRequest:
                        LOGGER.error(
                            "InvalidRequest executing batch: run_id=%s batch_size=%d batch_bytes=%d",
                            run.id,
                            batch_count,
                            batch_bytes,
                        )
                        raise
                    b = BatchQuery()
                    batch_count = 0
                    batch_bytes = 0
        if batch_count > 0:
            try:
                b.execute()
            except InvalidRequest:
                LOGGER.error(
                    "InvalidRequest executing batch: run_id=%s batch_size=%d batch_bytes=%d",
                    run.id,
                    batch_count,
                    batch_bytes,
                )
                raise

        total_events += run_event_count
        LOGGER.info(
            "Migrated %d events for run_id=%s",
            run_event_count,
            run.id,
        )

    LOGGER.warning(
        "Migration complete. runs_processed=%d skipped=%d events_migrated=%d parse_failures=%d",
        total_runs,
        skipped_runs,
        total_events,
        parse_failures,
    )


if __name__ == "__main__":
    migrate()
