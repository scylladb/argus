"""
Event Similarity Processor V2

This module processes SCT events by:
1. Reading unprocessed events from SCTUnprocessedEvent table
2. Sanitizing event messages
3. Generating embeddings using BGE-Small-EN model
4. Storing embeddings in separate tables (sct_error_event_embedding or sct_critical_event_embedding)
5. Removing processed events from unprocessed queue

Deduplication is scoped to a single run: an event's embedding is compared only
against the embeddings already stored for the same ``run_id``. Because ``run_id``
is the partition key of both embedding tables, this is a single-partition read,
so exact cosine over the partition is cheap and correct regardless of the total
table size.
"""

import logging
import time
from threading import Event
from uuid import UUID
from datetime import datetime

from chromadb.utils.distance_functions import cosine
from numpy import array

from argus.backend.models.argus_ai import SCTCriticalEventEmbedding, SCTErrorEventEmbedding
from argus.backend.plugins.sct.testrun import SCTUnprocessedEvent, SCTEvent
from argus.backend.util.logsetup import setup_application_logging
from argusAI.utils.scylla_connection import ScyllaConnection
from argusAI.utils.embedding import BgeSmallEnEmbeddingModel
from argusAI.utils.event_message_sanitizer import MessageSanitizer
from argusAI.utils.summary_dispatcher import SummaryDispatcher

LOGGER = logging.getLogger(__name__)
SLEEP_INTERVAL = 1  # Sleep for 1 second between processing cycles

# Maximum cosine distance for two embeddings to be considered duplicates.
DUPLICATE_DISTANCE_THRESHOLD = 0.05


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
        self.keyspace = (
            SCTCriticalEventEmbedding.__keyspace__
            or SCTErrorEventEmbedding.__keyspace__
            or self.db.config["SCYLLA_KEYSPACE_NAME"]
        )
        # Best-effort summarization of unique events, dispatched from the per-event pipeline.
        # Inert unless EVENT_SUMMARIZATION_ENABLED and OPENAI_API_KEY are configured; the
        # embedding path is never blocked or altered by it.
        self.summary_dispatcher = SummaryDispatcher(self.db, self.db.config)
        LOGGER.info("EventSimilarityProcessorV2 initialized")

    def _get_potential_duplicate_rows(self, run_id: UUID, table_name: str) -> list:
        """Read every embedding already stored for ``run_id`` (single-partition read)."""
        query = f"SELECT ts, embedding FROM {self.keyspace}.{table_name} WHERE run_id = ?"
        bound_statement = self.db.session.prepare(query)
        return list(self.db.session.execute(bound_statement, parameters=[run_id]))

    def _mark_event_is_duplicate(self, run_id: UUID, ts: datetime, severity: str, embedding: list[float]) -> bool:
        try:
            table_name = (
                SCTErrorEventEmbedding.__table_name__
                if severity == "ERROR"
                else SCTCriticalEventEmbedding.__table_name__
            )
            query_vector = array(embedding, dtype=float)
            dupe = next(
                (
                    row
                    for row in self._get_potential_duplicate_rows(run_id, table_name)
                    if row.ts != ts  # never match the event against its own stored embedding
                    and cosine(array(row.embedding, dtype=float), query_vector) < DUPLICATE_DISTANCE_THRESHOLD
                ),
                None,
            )
            if not dupe:
                return False
            q = f"SELECT event_id FROM {SCTEvent.__table_name__} WHERE run_id = ? AND severity = ? AND ts = ?"
            bound_q = self.db.session.prepare(q)
            dupe_event = self.db.session.execute(bound_q, parameters=(run_id, severity, dupe.ts)).one()
            if dupe_event is None:
                return False
            self._clear_unprocessed_event(SCTUnprocessedEvent.__table_name__, run_id, severity, ts)
            update_query = (
                f"UPDATE {SCTEvent.__table_name__} SET duplicate_id = ? WHERE run_id = ? AND severity = ? AND ts = ?"
            )
            self.db.execute(update_query, (dupe_event.event_id, run_id, severity, ts))
            return True
        except Exception as e:
            LOGGER.error(f"Duplicate search error: {e}", exc_info=True)
            raise

    def _clear_unprocessed_event(self, table_name: str, run_id: str, severity: str, ts: datetime):
        delete_query = f"DELETE FROM {table_name} WHERE run_id = ? AND severity = ? AND ts = ?"
        self.db.execute(delete_query, (run_id, severity, ts))

    def process_unprocessed_events(self) -> None:
        """
        Main processing loop that continuously reads and processes unprocessed events.
        """
        LOGGER.info("Starting event processing loop")
        while not self.stop_event.is_set():
            try:
                batch_processed = self._process_batch()
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

        # Step 3.6: Event is unique — dispatch summarization of the RAW message (not the
        # sanitized one) as a fire-and-forget background task. Never blocks Step 4.
        self.summary_dispatcher.dispatch(run_id, severity, ts, message)

        # Step 4: Store embedding in severity-specific table
        try:
            if severity == "ERROR":
                table_name = SCTErrorEventEmbedding.__table_name__
            elif severity == "CRITICAL":
                table_name = SCTCriticalEventEmbedding.__table_name__
            else:
                raise ValueError(f"Unsupported severity: {severity}")

            insert_query = f"INSERT INTO {self.keyspace}.{table_name} (run_id, ts, embedding) VALUES (?, ?, ?)"
            self.db.execute(insert_query, (run_id, ts, embedding))
            LOGGER.debug(f"Stored embedding in {table_name} for event: run_id={run_id}, ts={ts}")
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
        # Drain in-flight summarization tasks before closing the DB they write through.
        self.summary_dispatcher.shutdown()
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
