import os
from collections import namedtuple
from pathlib import Path
import chromadb
from threading import Thread, Event
import time
import logging
import datetime
from typing import Dict, Set, List, Tuple, Union
import uuid

from chromadb.api.types import IncludeEnum, Embeddings
from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
from chromadb.config import Settings

import itertools
from argus.backend.models.argus_ai import ErrorEventEmbeddings, CriticalEventEmbeddings
from argus.backend.plugins.sct.testrun import SCTTestRun
from argus.common.enums import TestStatus
from argusAI.utils.event_message_sanitizer import MessageSanitizer
from argusAI.utils.scylla_connection import ScyllaConnection

SLEEP_INTERVAL: int = 300  # 5 minutes
SIMILARITY_THRESHOLD: float = 0.90
MAX_SIMILARS: int = 20
DAYS_BACK: int = int(os.getenv('DAYS_BACK', '120'))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

EmbeddingEntry = namedtuple('EmbeddingEntry', ['run_id', 'event_index', 'embedding', 'start_time'])


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


LOGGER: logging.Logger = logging.getLogger(__name__)
stop_event: Event = Event()


class EventType:
    ERROR: str = "ERROR"
    CRITICAL: str = "CRITICAL"


class EventSimilarityProcessor:
    """
    EventSimilarityProcessor handles the processing of event embeddings, finding similarities,
    and updating the database with similar events for future display in Argus.
    """

    def __init__(self) -> None:
        """Initialize the EventProcessor with ChromaDB client and collections."""
        self._chromadb_client: chromadb.Client = chromadb.Client(Settings(anonymized_telemetry=False))
        self._collections: Dict[str, chromadb.Collection] = {
            EventType.ERROR: self._chromadb_client.get_or_create_collection("test_error_events"),
            EventType.CRITICAL: self._chromadb_client.get_or_create_collection("test_critical_events")
        }
        self._embedding_model: BgeSmallEnEmbeddingModel = BgeSmallEnEmbeddingModel()
        self._sanitizer: MessageSanitizer = MessageSanitizer()
        self._similars_found: int = 0
        self._db: ScyllaConnection = ScyllaConnection()
        LOGGER.info("Event Processor initialized with error and critical collections")

    def find_similarities(
            self,
            event_type: str,
            embedding_entry: EmbeddingEntry,
            similarity_threshold: float,
            max_similars: int
    ) -> None:
        """
        Find similar events in the collection and update the database.

        Args:
            event_type: Type of event (ERROR or CRITICAL)
            embedding_entry: Event data including run_id, event_index, and embedding
            similarity_threshold: Minimum similarity score for matches
            max_similars: Maximum number of similar events to find
        """
        collection: chromadb.Collection = self._collections[event_type]
        run_id: uuid.UUID = embedding_entry.run_id
        event_index: int = embedding_entry.event_index
        embedding: List[float] = embedding_entry.embedding

        LOGGER.info(f"Finding similarities for run_id: {run_id}, event_index: {event_index}, type: {event_type}")

        similar: Dict = collection.query(
            query_embeddings=[embedding],
            n_results=max_similars,
            where={"run_id": {"$ne": str(run_id)}},
            include=[
                IncludeEnum.metadatas,
                IncludeEnum.distances,
            ],
        )

        similar_map: Dict[uuid.UUID, int] = {}
        for j, distance in enumerate(similar["distances"][0]):
            if 1 - distance >= similarity_threshold:
                metadata: Dict[str, Union[str, int]] = similar["metadatas"][0][j]
                similar_map.update({uuid.UUID(metadata["run_id"]): metadata["idx"]})
                self._similars_found += 1
                if len(similar_map) >= max_similars:
                    break

        table = ErrorEventEmbeddings if event_type == EventType.ERROR else CriticalEventEmbeddings
        try:
            self._db.execute(
                f"UPDATE {table.__table_name__} SET similars_map = ? WHERE run_id = ? AND event_index = ?",
                (similar_map, run_id, event_index),
            )
            LOGGER.info(f"Found {len(similar_map)} similar {event_type} events for run_id: {run_id}, event_index: {event_index}")
        except Exception as e:
            LOGGER.error(f"Failed to update similars_map for run_id: {run_id}, event_index: {event_index}: {e}")

    def load_events(self, event_type: str, cutoff_time: datetime.datetime, batch_size: int = 5000
                    ) -> Tuple[Set[uuid.UUID], List[EmbeddingEntry]]:
        """
        Load historical events from ScyllaDB into ChromaDB.

        Args:
            event_type: Type of event to load (ERROR or CRITICAL)
            cutoff_time: Cutoff time for fetching events
            batch_size: Number of events to process in each batch

        Returns:
            Set of run IDs that were processed
            List of EmbeddingEntry objects for which similarities need to be found
        """
        processed_runs: Set[uuid.UUID] = set()
        collection: chromadb.Collection = self._collections[event_type]
        table = ErrorEventEmbeddings if event_type == EventType.ERROR else CriticalEventEmbeddings
        similars_to_update: List[EmbeddingEntry] = []

        LOGGER.info(f"Loading processed {event_type} events...")
        query: str = f"SELECT * FROM {table.__table_name__} WHERE start_time > ? ALLOW FILTERING BYPASS CACHE"
        rows = self._db.execute(query, (cutoff_time,))
        iterator = iter(rows)

        batch_count: int = 0
        while True:
            batch = list(itertools.islice(iterator, batch_size))
            if not batch:
                break

            ids: List[str] = []
            embeddings_list: List[List[float]] = []
            metadatas: List[Dict[str, Union[str, int]]] = []
            for emb in batch:
                processed_runs |= {emb.run_id}
                ids.append(f"{emb.run_id}_{emb.event_index}")
                embeddings_list.append(emb.embedding)
                metadatas.append({"run_id": str(emb.run_id), "idx": emb.event_index})
                if emb.similars_map is None:
                    similars_to_update.append(EmbeddingEntry(emb.run_id, emb.event_index, emb.embedding, emb.start_time))

            if ids:
                collection.upsert(ids=ids, embeddings=embeddings_list, metadatas=metadatas)
                batch_count += 1
                LOGGER.info(f"Loaded batch {batch_count} of {event_type} events")
        return processed_runs, similars_to_update

    def process_new_events(self, cutoff_time: datetime.datetime, processed_runs: Set[uuid.UUID],
                           similars_to_find: Dict[str, List[EmbeddingEntry]]) -> None:
        """
        Continuously process new events from test runs.

        Args:
            cutoff_time: Cutoff time for fetching new test runs
            processed_runs: Set of run IDs that have already been processed
        """
        new_embeddings: Dict[str, List[EmbeddingEntry]] = similars_to_find
        while not stop_event.is_set():
            LOGGER.info(f"Starting event processing cycle; fetching tests since: {cutoff_time}")
            tests_to_process_result = self._db.execute(
                f"SELECT id, status FROM {SCTTestRun.table_name()} WHERE start_time > ? ALLOW FILTERING BYPASS CACHE",
                (cutoff_time,)
            )
            tests_to_process: Set[uuid.UUID] = {run.id for run in tests_to_process_result if
                                                run.status != TestStatus.PASSED.value} - processed_runs
            LOGGER.info(f"tests to process (including in progress) count: {len(tests_to_process)}")
            try:
                stats: Dict[str, int] = {EventType.ERROR: len(similars_to_find[EventType.ERROR]),
                                         EventType.CRITICAL: len(similars_to_find[EventType.CRITICAL])}
                embedding_start_time: float = time.time()
                self._similars_found = 0
                for run_id in tests_to_process:
                    test_run = self._db.execute(
                        f"SELECT id, start_time, events FROM {SCTTestRun.table_name()} WHERE id = ? BYPASS CACHE",
                        (run_id,)
                    ).one()
                    if not test_run or not test_run.events:
                        continue
                    LOGGER.info(f"Processing test run {test_run.id}...")
                    for idx, event in enumerate(test_run.events):
                        if not hasattr(event, "severity") or event.severity not in stats or not event.last_events:
                            continue

                        event_type: str = event.severity
                        event_texts: List[str] = [self._sanitizer.sanitize(test_run.id, event_text) for event_text in event.last_events]

                        if not event_texts:
                            continue

                        embeddings: Embeddings = self._embedding_model(event_texts)
                        table = ErrorEventEmbeddings if event_type == EventType.ERROR else CriticalEventEmbeddings

                        for event_idx, embedding in enumerate(embeddings):
                            event_id: str = f"{test_run.id}_{idx}_{event_idx}"
                            metadata: Dict[str, Union[str, int]] = {"run_id": str(test_run.id), "idx": event_idx}
                            self._collections[event_type].upsert(
                                ids=[event_id],
                                embeddings=[embedding],
                                metadatas=[metadata],
                            )

                            query: str = f"INSERT INTO {table.__table_name__} (run_id, event_index, embedding, start_time) VALUES (?, ?, ?, ?)"
                            embedding_list: List[float] = list(embedding) if not isinstance(embedding, list) else embedding
                            self._db.execute(query, (test_run.id, event_idx, embedding_list, test_run.start_time))

                            emb = EmbeddingEntry(
                                run_id=test_run.id,
                                event_index=event_idx,
                                embedding=embedding,
                                start_time=test_run.start_time
                            )
                            new_embeddings[event_type].append(emb)
                            stats[event_type] += 1
                    processed_runs |= {test_run.id}

                cutoff_time = datetime.datetime.now() - datetime.timedelta(days=7)
                embedding_time: float = time.time() - embedding_start_time
                similarity_time: float = 0

                if any(stats.values()):
                    LOGGER.info(f"Processed {stats[EventType.ERROR]} new error events and {stats[EventType.CRITICAL]} new critical events")
                    for event_type, embeddings in new_embeddings.items():
                        if embeddings:
                            LOGGER.info(f"Computing similarities for new {event_type} embeddings")
                            similarity_start_time: float = time.time()

                            for emb in embeddings:
                                self.find_similarities(event_type, emb, SIMILARITY_THRESHOLD, MAX_SIMILARS)
                            similarity_time = time.time() - similarity_start_time
                else:
                    LOGGER.info("No new events found")

            except Exception as e:
                LOGGER.error(f"Error in event processing cycle: {str(e)}", exc_info=True)
                embedding_time = 0
                similarity_time = 0

            LOGGER.info(
                f"Cycle complete; embedding time: {embedding_time:.2f} seconds; similarity time: {similarity_time:.2f} seconds; Found {self._similars_found} similars; sleeping for {SLEEP_INTERVAL} seconds")
            new_embeddings = {EventType.ERROR: [], EventType.CRITICAL: []}
            stop_event.wait(timeout=SLEEP_INTERVAL)

    def shutdown(self) -> None:
        """Shut down the ScyllaDB connection and any other resources."""
        self._db.shutdown()
        LOGGER.info("EventProcessor shut down")


if __name__ == "__main__":
    LOGGER.info("Starting Event Similarity Processor...")
    processor: EventSimilarityProcessor = EventSimilarityProcessor()
    cutoff_time: datetime.datetime = datetime.datetime.now() - datetime.timedelta(days=DAYS_BACK)
    LOGGER.info(f"Processing all tests runs since: {cutoff_time}")
    processed_error_runs, error_similars_to_find = processor.load_events(EventType.ERROR, cutoff_time)
    processed_critical_runs, critical_similars_to_find = processor.load_events(EventType.CRITICAL, cutoff_time)
    thread: Thread = Thread(
        target=processor.process_new_events,
        args=(cutoff_time, processed_error_runs | processed_critical_runs,
              {EventType.ERROR: error_similars_to_find, EventType.CRITICAL: critical_similars_to_find}),
        daemon=True,
    )
    thread.start()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        LOGGER.info("Stopping Event Similarity Processor...")
        stop_event.set()
        thread.join(timeout=60)
        processor.shutdown()
        LOGGER.info("Event Similarity Processor stopped")
