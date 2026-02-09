"""
Event Similarity Processor V2

This module processes SCT events by:
1. Reading unprocessed events from SCTUnprocessedEvent table
2. Sanitizing event messages
3. Generating embeddings using BGE-Small-EN model
4. Storing embeddings in separate tables (sct_error_event_embedding or sct_critical_event_embedding)
5. Removing processed events from unprocessed queue
"""

from collections import namedtuple
import logging
import time
from pathlib import Path
from threading import Event
from typing import Literal
from uuid import UUID
from datetime import datetime

from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
from chromadb.utils.distance_functions import cosine
from numpy import array

from argus.backend.models.argus_ai import SCTCriticalEventEmbedding, SCTErrorEventEmbedding
from argus.backend.plugins.sct.testrun import SCTUnprocessedEvent, SCTEvent
from argus.backend.util.logsetup import setup_application_logging
from argusAI.utils.scylla_connection import ScyllaConnection
from argusAI.utils.event_message_sanitizer import MessageSanitizer

LOGGER = logging.getLogger(__name__)
SLEEP_INTERVAL = 1  # Sleep for 1 second between processing cycles

SimilarEvent = namedtuple("SimilarEvent", ["run_id", "ts", "embedding", "added_ts"])
Severity = Literal["ERROR", "CRITICAL"]
RunIdStr = str


class BgeSmallEnEmbeddingModel(ONNXMiniLM_L6_V2):
    """
    Compact English text embedding model by BAAI, released Sep 2023.
    Trained on large-scale paired data with RetroMAE and contrastive learning.
    Produces high-quality 384-dim embeddings, optimized for efficiency in semantic search, classification, and clustering.
    """

    MODEL_NAME: str = "bge-small-en-v1.5"
    DOWNLOAD_PATH: Path = Path.home() / ".cache" / "chroma" / "onnx_models" / MODEL_NAME
    EXTRACTED_FOLDER_NAME: str = "onnx"
    ARCHIVE_FILENAME: str = "onnx.tar.gz"
    MODEL_DOWNLOAD_URL: str = (
        "https://scylla-qa-public.s3.us-east-1.amazonaws.com/ArgusAI/bge-small-en-v1.5/onnx.tar.gz"
    )
    _MODEL_SHA256: str = "e7d1743b0c08f55c687cff6af696683398682f9ab4fb3cad1be644ee5553a72d"


class EventSimilarityProcessorV2:
    """
    Processes unprocessed SCT events by generating embeddings and storing them in severity-specific tables.
    """

    def __init__(self, stop_event: Event | None = None) -> None:
        """
        Initialize the processor with embedding model and sanitizer.

        Args:
            stop_event: Optional threading.Event to signal shutdown
        """
        self.embedding_model = BgeSmallEnEmbeddingModel()
        self.sanitizer = MessageSanitizer()
        self.stop_event = stop_event or Event()
        self.db = ScyllaConnection()
        self.processed_count = 0
        self.error_count = 0
        self.cache_clear_timer = 3600
        self.similar_event_cache: dict[tuple[RunIdStr, Severity], list[SimilarEvent]] = {}
        LOGGER.info("EventSimilarityProcessorV2 initialized")

    def _clear_stale_cache(self):
        def cmp_ts(ts: datetime | float):
            match ts:
                case float():
                    return ts + self.cache_clear_timer > time.time()
                case datetime():
                    return ts.timestamp() + self.cache_clear_timer > time.time()

        for key in list(self.similar_event_cache.keys()):
            full_cache = [event for event in self.similar_event_cache[key] if cmp_ts(getattr(event, "added_ts", 0.0))]
            if len(full_cache) == 0:
                self.similar_event_cache.pop(key)

    @staticmethod
    def is_stale(cache: SimilarEvent, rows: list[SimilarEvent]):
        for row in rows:
            if cache.run_id == row.run_id and cache.ts.timestamp() == row.ts.timestamp():
                return True
        return False

    def _get_potential_duplicate_rows(self, embedding: list[float], table_name: str) -> list[SimilarEvent]:
        query = f"""
                SELECT run_id, ts, embedding
                FROM {table_name}
                ORDER BY embedding ANN OF ?
                LIMIT ?
            """
        bound_statement = self.db.session.prepare(query)
        result_rows = list(self.db.session.execute(bound_statement, parameters=[embedding, 1000]))

        return result_rows

    def _merge_cache(
        self, run_id: str, severity: str, result_rows: list[SimilarEvent]
    ) -> tuple[list[SimilarEvent], list[SimilarEvent]]:
        # Remove stale entries from cache if they exist in VS set
        cached_events = self.similar_event_cache.get((run_id, severity), [])
        new_cache = [cached for cached in cached_events if not self.is_stale(cached, result_rows)]
        self.similar_event_cache[(run_id, severity)] = new_cache
        rows = [*new_cache, *result_rows]

        return rows, new_cache

    def _mark_event_is_duplicate(self, run_id: str, ts: datetime, severity: str, embedding: list[float]) -> bool:
        try:
            table_name = (
                SCTErrorEventEmbedding.__table_name__
                if severity == "ERROR"
                else SCTCriticalEventEmbedding.__table_name__
            )
            rows, _ = self._merge_cache(run_id, severity, self._get_potential_duplicate_rows(embedding, table_name))
            if len(rows) > 0:
                dupe_embeddings = [
                    (row, cosine(array(row.embedding, dtype=float), array(embedding, dtype=float)))
                    for row in rows
                    if row.run_id == run_id
                ]
                if len(dupe_embeddings) == 0:
                    return False
                dupe_embedding = next((row for row, distance in dupe_embeddings if -0.1 < distance < 0.1), None)
                if not dupe_embedding:
                    return False
                q = f"SELECT event_id FROM {SCTEvent.__table_name__} WHERE run_id = ? AND severity = ? AND ts = ?"
                bound_q = self.db.session.prepare(q)
                dupe = self.db.session.execute(
                    bound_q, parameters=(dupe_embedding.run_id, severity, dupe_embedding.ts)
                ).one()
                dupe_id = dupe.event_id
                self._clear_unprocessed_event(SCTUnprocessedEvent.__table_name__, run_id, severity, ts)
                update_query = f"UPDATE {SCTEvent.__table_name__} SET duplicate_id = ? WHERE run_id = ? AND severity = ? AND ts = ?"
                self.db.execute(update_query, (dupe_id, run_id, severity, ts))
                return True
        except Exception as e:
            LOGGER.error(f"Duplicate search error: {e}", exc_info=True)
            raise

        return False

    def _clear_unprocessed_event(self, table_name: str, run_id: str, severity: str, ts: datetime):
        delete_query = f"DELETE FROM {table_name} WHERE run_id = ? AND severity = ? AND ts = ?"
        self.db.execute(delete_query, (run_id, severity, ts))

    def process_unprocessed_events(self) -> None:
        """
        Main processing loop that continuously reads and processes unprocessed events.
        """
        LOGGER.info("Starting event processing loop")
        next_clear_ts = time.time() + self.cache_clear_timer
        while not self.stop_event.is_set():
            try:
                batch_processed = self._process_batch()
                if time.time() > next_clear_ts:
                    self._clear_stale_cache()
                    next_clear_ts = time.time() + self.cache_clear_timer
                if batch_processed == 0:
                    # No events to process, sleep before next iteration
                    time.sleep(SLEEP_INTERVAL)
                else:
                    LOGGER.info(f"Processed {batch_processed} events in this batch")
            except Exception as e:
                LOGGER.error(f"Error in processing loop: {e}", exc_info=True)
                self.error_count += 1
                time.sleep(SLEEP_INTERVAL)

        LOGGER.info(f"Processing loop stopped. Total processed: {self.processed_count}, Errors: {self.error_count}")

    def _process_batch(self, batch_size: int = 100) -> int:
        """
        Process a batch of unprocessed events.

        Args:
            batch_size: Maximum number of events to process in one batch

        Returns:
            Number of events processed in this batch
        """
        # Fetch unprocessed events using raw query
        query = f"SELECT run_id, severity, ts FROM {SCTUnprocessedEvent.__table_name__} LIMIT {batch_size}"
        try:
            rows = self.db.execute(query)
            unprocessed_events = list(rows)
        except Exception as e:
            LOGGER.error(f"Failed to fetch unprocessed events: {e}", exc_info=True)
            return 0

        if not unprocessed_events:
            return 0

        processed_in_batch = 0

        for event_row in unprocessed_events:
            try:
                self._process_single_event(run_id=event_row.run_id, severity=event_row.severity, ts=event_row.ts)
                processed_in_batch += 1
                self.processed_count += 1
            except Exception as e:
                LOGGER.error(
                    f"Failed to process event (run_id={event_row.run_id}, "
                    f"severity={event_row.severity}, ts={event_row.ts}): {e}",
                    exc_info=True,
                )
                self.error_count += 1
                # Still delete the unprocessed event to avoid infinite retries
                delete_query = (
                    f"DELETE FROM {SCTUnprocessedEvent.__table_name__} WHERE run_id = ? AND severity = ? AND ts = ?"
                )
                self.db.execute(delete_query, (event_row.run_id, event_row.severity, event_row.ts))
        self._clear_stale_cache()
        return processed_in_batch

    def _process_single_event(self, run_id: UUID, severity: str, ts: datetime) -> None:
        """
        Process a single event: read, sanitize, embed, store, and cleanup.

        Args:
            run_id: Test run UUID
            severity: Event severity (ERROR or CRITICAL)
            ts: Event timestamp

        Raises:
            Exception: If event not found or embedding generation fails
        """
        LOGGER.debug(f"Processing event: run_id={run_id}, severity={severity}, ts={ts}")

        # Step 1: Read event message from SCTEvent table
        try:
            query = f"SELECT message FROM {SCTEvent.__table_name__} WHERE run_id = ? AND severity = ? AND ts = ?"
            result = self.db.execute(query, (run_id, severity, ts))
            event = result.one()
            if not event:
                raise ValueError("Event not found")
        except Exception:
            LOGGER.warning(f"Event not found in SCTEvent table: run_id={run_id}, severity={severity}, ts={ts}")
            raise

        message = event.message
        if not message:
            LOGGER.warning(f"Event has no message: run_id={run_id}, severity={severity}, ts={ts}")
            raise ValueError("Event message is empty")

        # Step 2: Sanitize event message
        try:
            sanitized_message = self.sanitizer.sanitize(run_id, message)
        except Exception as e:
            LOGGER.error(f"Failed to sanitize message for event (run_id={run_id}): {e}", exc_info=True)
            raise

        if not sanitized_message or not sanitized_message.strip():
            LOGGER.warning(f"Sanitized message is empty for event: run_id={run_id}, severity={severity}, ts={ts}")
            raise ValueError("Sanitized message is empty")

        # Step 3: Generate embedding
        try:
            embeddings = self.embedding_model([sanitized_message])
            if not embeddings or len(embeddings) == 0:
                raise ValueError("Embedding generation returned empty result")
            embedding = embeddings[0]
        except Exception as e:
            LOGGER.error(f"Failed to generate embedding for event (run_id={run_id}): {e}", exc_info=True)
            raise

        # Step 3.5: Check if event is duplicate, cancel remaining steps if it is.
        if self._mark_event_is_duplicate(run_id, ts, severity, embedding):
            return

        # Step 4: Store embedding in severity-specific table
        try:
            if severity == "ERROR":
                table_name = SCTErrorEventEmbedding.__table_name__
            elif severity == "CRITICAL":
                table_name = SCTCriticalEventEmbedding.__table_name__
            else:
                raise ValueError(f"Unsupported severity: {severity}")

            insert_query = f"INSERT INTO {table_name} (run_id, ts, embedding) VALUES (?, ?, ?)"
            self.db.execute(insert_query, (run_id, ts, embedding))
            LOGGER.debug(f"Stored embedding in {table_name} for event: run_id={run_id}, ts={ts}")
            # cache event until it is visible in VS
            cache = self.similar_event_cache.get((run_id, severity))
            if not cache:
                cache: list[SimilarEvent] = []
            cache.append(SimilarEvent(run_id, ts, embedding, time.time()))
            self.similar_event_cache[(run_id, severity)] = cache
        except Exception as e:
            LOGGER.error(f"Failed to store embedding for event (run_id={run_id}): {e}", exc_info=True)
            raise

        # Step 5: Remove entry from unprocessed_events table
        try:
            self._clear_unprocessed_event(SCTUnprocessedEvent.__table_name__, run_id, severity, ts)
            LOGGER.debug(f"Removed unprocessed event: run_id={run_id}, severity={severity}, ts={ts}")
        except Exception as e:
            LOGGER.error(f"Failed to delete unprocessed event (run_id={run_id}): {e}", exc_info=True)
            raise

    def shutdown(self) -> None:
        """Shutdown the processor and cleanup resources."""
        self.stop_event.set()
        self.db.shutdown()
        LOGGER.info("EventSimilarityProcessorV2 shutdown complete")


def main():
    """Main entry point for the event similarity processor."""
    setup_application_logging(log_level=logging.INFO)

    LOGGER.info("Starting Event Similarity Processor V2...")

    stop_event = Event()
    processor = EventSimilarityProcessorV2(stop_event=stop_event)

    try:
        processor.process_unprocessed_events()
    except KeyboardInterrupt:
        LOGGER.info("Received keyboard interrupt, shutting down...")
    finally:
        processor.shutdown()
        LOGGER.info("Event Similarity Processor V2 stopped")


if __name__ == "__main__":
    main()
