import os
from collections import namedtuple
from pathlib import Path
import chromadb
from threading import Thread, Event
import time
import logging
import datetime
import uuid

from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
from chromadb.config import Settings

import itertools
from argus.backend.models.argus_ai import ErrorEventEmbeddings, CriticalEventEmbeddings
from argus.backend.plugins.sct.testrun import SCTTestRun
from argusAI.utils.event_message_sanitizer import MessageSanitizer
from argusAI.utils.scylla_connection import ScyllaConnection

SLEEP_INTERVAL = 300  # 5 minutes
SIMILARITY_THRESHOLD = 0.90
MAX_SIMILARS = 20
DAYS_BACK = int(os.getenv('DAYS_BACK', 120))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

EmbeddingEntry = namedtuple('EmbeddingEntry', ['run_id', 'event_index', 'embedding', 'start_time'])

class BGE_SMALL(ONNXMiniLM_L6_V2):
    """
    Compact English text embedding model by BAAI, released Sep 2023.
    Trained on large-scale paired data with RetroMAE and contrastive learning.
    Produces high-quality 384-dim embeddings, optimized for efficiency in semantic search, classification, and clustering.
    """
    MODEL_NAME = "bge-small-en-v1.5"
    DOWNLOAD_PATH = Path.home() / ".cache" / "chroma" / "onnx_models" / MODEL_NAME
    EXTRACTED_FOLDER_NAME = "onnx"
    ARCHIVE_FILENAME = "onnx.tar.gz"
    MODEL_DOWNLOAD_URL = (
        "https://scylla-qa-public.s3.us-east-1.amazonaws.com/ArgusAI/bge-small-en-v1.5/onnx.tar.gz"
    )
    _MODEL_SHA256 = "e7d1743b0c08f55c687cff6af696683398682f9ab4fb3cad1be644ee5553a72d"

logger = logging.getLogger(__name__)
stop_event = Event()

class EventType:
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class EventProcessor:
    def __init__(self):
        """Initialize the EventProcessor with ChromaDB client and collections."""
        self.chromadb_client = chromadb.Client(Settings(anonymized_telemetry=False))
        self.collections = {
            EventType.ERROR: self.chromadb_client.get_or_create_collection("test_error_events"),
            EventType.CRITICAL: self.chromadb_client.get_or_create_collection("test_critical_events")
        }
        self.embedding_model = BGE_SMALL()
        self.sanitizer = MessageSanitizer()
        self.similars_found = 0
        self.db = ScyllaConnection()
        logger.info("Event Processor initialized with error and critical collections")

    def find_similarities(self, event_type, embedding_entry, similarity_threshold, max_similars):
        """
        Find similar events in the collection and update the database.

        Args:
            event_type (str): Type of event (ERROR or CRITICAL)
            embedding_entry (dict): Event data including run_id, event_index, and embedding
            similarity_threshold (float): Minimum similarity score for matches
            max_similars (int): Maximum number of similar events to find
        """
        collection = self.collections[event_type]
        run_id = embedding_entry.run_id
        event_index = embedding_entry.event_index
        embedding = embedding_entry.embedding

        logger.info(f"Finding similarities for run_id: {run_id}, event_index: {event_index}, type: {event_type}")

        similar = collection.query(
            query_embeddings=[embedding],
            n_results=max_similars,
            where={"run_id": {"$ne": str(run_id)}},
            include=["metadatas", "distances"],
        )

        similar_map = {}
        for j, distance in enumerate(similar["distances"][0]):
            if 1 - distance >= similarity_threshold:
                metadata = similar["metadatas"][0][j]
                similar_map.update({uuid.UUID(metadata["run_id"]): metadata["idx"]})
                self.similars_found += 1
                if len(similar_map) >= max_similars:
                    break

        table = ErrorEventEmbeddings if event_type == EventType.ERROR else CriticalEventEmbeddings
        try:
            self.db.execute(
                f"UPDATE {table.__table_name__} SET similars_map = %s WHERE run_id = %s AND event_index = %s",
                (similar_map, run_id, event_index),
            )
            logger.info(f"Found {len(similar_map)} similar {event_type} events for run_id: {run_id}, event_index: {event_index}")
        except Exception as e:
            logger.error(f"Failed to update similars_map for run_id: {run_id}, event_index: {event_index}: {e}")

    def load_events(self, event_type, days_back, batch_size=5000):
        """
        Load historical events from ScyllaDB into ChromaDB.

        Args:
            event_type (str): Type of event to load (ERROR or CRITICAL)
            days_back (int): Number of days to look back for events
            batch_size (int): Number of events to process in each batch

        Returns:
            datetime: Most recent timestamp found in the loaded events
        """
        collection = self.collections[event_type]
        table = ErrorEventEmbeddings if event_type == EventType.ERROR else CriticalEventEmbeddings
        cutoff_time = datetime.datetime.now() - datetime.timedelta(days=days_back)
        most_recent_time = cutoff_time
        to_update = []

        logger.info(f"Loading {event_type} events...")
        query = f"SELECT * FROM {table.__table_name__} WHERE start_time > %s ALLOW FILTERING BYPASS CACHE"
        rows = self.db.execute(query, (cutoff_time,))
        iterator = iter(rows)

        batch_count = 0
        while True:
            batch = list(itertools.islice(iterator, batch_size))
            if not batch:
                break

            ids, embeddings_list, metadatas = [], [], []
            for emb in batch:
                ids.append(f"{emb.run_id}_{emb.event_index}")
                embeddings_list.append(emb.embedding)
                metadatas.append({"run_id": str(emb.run_id), "idx": emb.event_index})
                if emb.start_time > most_recent_time:
                    most_recent_time = emb.start_time
                if emb.similars_map is None:
                    to_update.append(EmbeddingEntry(emb.run_id, emb.event_index, emb.embedding, emb.start_time))

            if ids:
                collection.upsert(ids=ids, embeddings=embeddings_list, metadatas=metadatas)
                batch_count += 1
                logger.info(f"Loaded batch {batch_count} of {event_type} events")

        for emb in to_update:
            self.find_similarities(event_type, emb, SIMILARITY_THRESHOLD, MAX_SIMILARS)

        return most_recent_time


    def process_new_events(self, last_processed_time):
        """
        Continuously process new events from test runs.

        Args:
            last_processed_time (datetime): Timestamp of the last processed event
        """
        while not stop_event.is_set():
            logger.info(f"Starting event processing cycle; last processed time: {last_processed_time}")
            try:
                query = f"SELECT id, start_time, events FROM {SCTTestRun.table_name()} WHERE start_time > %s ALLOW FILTERING BYPASS CACHE"
                test_runs = self.db.execute(query, (last_processed_time,))

                stats = {EventType.ERROR: 0, EventType.CRITICAL: 0}
                new_embeddings = {EventType.ERROR: [], EventType.CRITICAL: []}

                embedding_start_time = time.time()
                self.similars_found = 0
                for test_run in test_runs:
                    if not test_run.events:
                        continue
                    logger.info(f"Processing test run {test_run.id}...")
                    for idx, event in enumerate(test_run.events):
                        if not hasattr(event, "severity") or event.severity not in stats or not event.last_events:
                            continue

                        event_type = event.severity
                        event_texts = [self.sanitizer.sanitize(test_run.id, event_text) for event_text in event.last_events]

                        if not event_texts:
                            continue

                        embeddings = self.embedding_model(event_texts)
                        table = ErrorEventEmbeddings if event_type == EventType.ERROR else CriticalEventEmbeddings

                        for event_idx, embedding in enumerate(embeddings):
                            event_id = f"{test_run.id}_{idx}_{event_idx}"
                            metadata = {"run_id": str(test_run.id), "idx": event_idx}
                            self.collections[event_type].upsert(
                                ids=[event_id],
                                embeddings=[embedding],
                                metadatas=[metadata],
                            )

                            query = f"INSERT INTO {table.__table_name__} (run_id, event_index, embedding, start_time) VALUES (%s, %s, %s, %s)"
                            embedding_list = list(embedding) if not isinstance(embedding, list) else embedding
                            self.db.execute(query, (test_run.id, event_idx, embedding_list, test_run.start_time))

                            emb = EmbeddingEntry(
                                run_id=test_run.id,
                                event_index=event_idx,
                                embedding=embedding,
                                start_time=test_run.start_time
                            )
                            new_embeddings[event_type].append(emb)
                            stats[event_type] += 1

                        if test_run.start_time > last_processed_time:
                            last_processed_time = test_run.start_time

                embedding_time = time.time() - embedding_start_time
                similarity_time = 0

                if any(stats.values()):
                    logger.info(f"Processed {stats[EventType.ERROR]} new error events and {stats[EventType.CRITICAL]} new critical events")
                    for event_type, embeddings in new_embeddings.items():
                        if embeddings:
                            logger.info(f"Computing similarities for new {event_type} embeddings")
                            similarity_start_time = time.time()

                            for emb in embeddings:
                                self.find_similarities(event_type, emb, SIMILARITY_THRESHOLD, MAX_SIMILARS)
                            similarity_time = time.time() - similarity_start_time
                else:
                    logger.info("No new events found")

            except Exception as e:
                logger.error(f"Error in event processing cycle: {str(e)}", exc_info=True)
                embedding_time = 0
                similarity_time = 0

            logger.info(
                f"Cycle complete; embedding time: {embedding_time:.2f} seconds; similarity time: {similarity_time:.2f} seconds; Found {self.similars_found} similars; sleeping for {SLEEP_INTERVAL} seconds")
            stop_event.wait(timeout=SLEEP_INTERVAL)

    def shutdown(self):
        """Shut down the ScyllaDB connection and any other resources."""
        self.db.shutdown()
        logger.info("EventProcessor shut down")

if __name__ == "__main__":
    logger.info("Starting Event Similarity Processor...")
    processor = EventProcessor()
    last_processed_time = max(
        processor.load_events(EventType.ERROR, DAYS_BACK),
        processor.load_events(EventType.CRITICAL, DAYS_BACK)
    )
    logger.info(f"Initial last processed time set to: {last_processed_time}")
    thread = Thread(
        target=processor.process_new_events,
        args=(last_processed_time,),
        daemon=True,
    )
    thread.start()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Stopping Event Similarity Processor...")
        stop_event.set()
        thread.join(timeout=60)
        processor.shutdown()
        logger.info("Event Similarity Processor stopped")
