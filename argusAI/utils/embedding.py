from pathlib import Path
from uuid import UUID

from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

from argusAI.utils.event_message_sanitizer import MessageSanitizer

_ZERO_UUID = UUID(int=0)


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


class EventEmbedder:
    """The single place that turns an event message into an embedding: sanitize (strip
    run-specific noise) then embed with BGE-small-en. Shared by the similarity worker and
    the eval's similarity dedup so both produce identical vectors from identical inputs."""

    def __init__(self, write_log: bool = True):
        self.sanitizer = MessageSanitizer(write_log=write_log)
        self.model = BgeSmallEnEmbeddingModel()

    def embed(self, message: str, run_id: UUID = _ZERO_UUID) -> list[float]:
        sanitized = self.sanitizer.sanitize(run_id, message)
        if not sanitized or not sanitized.strip():
            raise ValueError("Sanitized message is empty")
        vectors = self.model([sanitized])
        if not vectors:
            raise ValueError("Embedding generation returned empty result")
        return vectors[0]

    def embed_many(self, messages: list[str], run_id: UUID = _ZERO_UUID) -> list:
        sanitized = [self.sanitizer.sanitize(run_id, m) for m in messages]
        return self.model(sanitized)
