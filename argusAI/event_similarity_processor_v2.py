"""
Event Similarity Processor V2

This module processes SCT events by:
1. Reading unprocessed events from sct_unprocessed_events table
2. Sanitizing event messages
3. Generating embeddings using BGE-Small-EN model
4. Storing embeddings in separate tables (sct_error_event_embedding or sct_critical_event_embedding)
5. Removing processed events from unprocessed queue
"""

import logging
import time
from pathlib import Path
from threading import Event
from uuid import UUID
from datetime import datetime

from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

from argusAI.utils.scylla_connection import ScyllaConnection
from argusAI.utils.event_message_sanitizer import MessageSanitizer

LOGGER = logging.getLogger(__name__)
SLEEP_INTERVAL = 1  # Sleep for 1 second between processing cycles


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
        LOGGER.info("EventSimilarityProcessorV2 initialized")

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
        query = f"SELECT run_id, severity, ts FROM sct_unprocessed_events LIMIT {batch_size}"
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
                delete_query = "DELETE FROM sct_unprocessed_events WHERE run_id = ? AND severity = ? AND ts = ?"
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
            query = "SELECT message FROM sct_event WHERE run_id = ? AND severity = ? AND ts = ?"
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

        # Step 4: Store embedding in severity-specific table
        try:
            if severity == "ERROR":
                table_name = "sct_error_event_embedding"
            elif severity == "CRITICAL":
                table_name = "sct_critical_event_embedding"
            else:
                raise ValueError(f"Unsupported severity: {severity}")

            insert_query = f"INSERT INTO {table_name} (run_id, ts, embedding) VALUES (?, ?, ?)"
            self.db.execute(insert_query, (run_id, ts, embedding))
            LOGGER.debug(f"Stored embedding in {table_name} for event: run_id={run_id}, ts={ts}")
        except Exception as e:
            LOGGER.error(f"Failed to store embedding for event (run_id={run_id}): {e}", exc_info=True)
            raise

        # Step 5: Remove entry from unprocessed_events table
        try:
            delete_query = "DELETE FROM sct_unprocessed_events WHERE run_id = ? AND severity = ? AND ts = ?"
            self.db.execute(delete_query, (run_id, severity, ts))
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

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
