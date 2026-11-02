import hashlib
import logging
import os
import shutil
import tarfile
import tempfile
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import requests
from tokenizers import Tokenizer

from argus.backend.plugins.sct.events.sanitizer import MessageSanitizer

LOGGER = logging.getLogger(__name__)


class EmbeddingModelError(Exception):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cosine(x: np.ndarray, y: np.ndarray) -> float:
    return float(1.0 - np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-30))


class BgeSmallEnEmbeddingModel:
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
    MAX_TOKENS: int = 256
    BATCH_SIZE: int = 32
    DOWNLOAD_ATTEMPTS: int = 3

    def __init__(self) -> None:
        self._tokenizer: Tokenizer | None = None
        self._session: ort.InferenceSession | None = None

    def __call__(self, texts: list[str]) -> list[np.ndarray]:
        if self._session is None:
            self._load()
        vectors = []
        for start in range(0, len(texts), self.BATCH_SIZE):
            vectors.extend(self._embed_batch(texts[start : start + self.BATCH_SIZE]))
        return vectors

    def _load(self) -> None:
        model_dir = self.DOWNLOAD_PATH / self.EXTRACTED_FOLDER_NAME
        if not self._is_extracted():
            self._extract_archive()

        tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=self.MAX_TOKENS)
        tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=self.MAX_TOKENS)

        options = ort.SessionOptions()
        options.log_severity_level = 3
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(
            str(model_dir / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._tokenizer = tokenizer

    def _is_extracted(self) -> bool:
        model_dir = self.DOWNLOAD_PATH / self.EXTRACTED_FOLDER_NAME
        return (model_dir / "model.onnx").exists() and (model_dir / "tokenizer.json").exists()

    def _extract_archive(self) -> None:
        archive = self.DOWNLOAD_PATH / self.ARCHIVE_FILENAME
        if not (archive.exists() and _sha256(archive) == self._MODEL_SHA256):
            self._download(archive)
        staging = Path(tempfile.mkdtemp(dir=self.DOWNLOAD_PATH, prefix=".extract-"))
        try:
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(staging, filter="data")
            try:
                os.rename(staging / self.EXTRACTED_FOLDER_NAME, self.DOWNLOAD_PATH / self.EXTRACTED_FOLDER_NAME)
            except OSError:
                if not self._is_extracted():
                    raise
                LOGGER.info("Another process extracted %s first", self.MODEL_NAME)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _download(self, archive: Path) -> None:
        archive.parent.mkdir(parents=True, exist_ok=True)
        partial = archive.with_name(f"{archive.name}.{os.getpid()}.part")
        for attempt in range(1, self.DOWNLOAD_ATTEMPTS + 1):
            try:
                with requests.get(self.MODEL_DOWNLOAD_URL, stream=True, timeout=60) as response:
                    response.raise_for_status()
                    with partial.open("wb") as file:
                        for chunk in response.iter_content(chunk_size=1 << 20):
                            file.write(chunk)
                if _sha256(partial) == self._MODEL_SHA256:
                    os.replace(partial, archive)
                    return
                failure = EmbeddingModelError(f"{self.MODEL_DOWNLOAD_URL} does not match the expected SHA-256")
            except requests.RequestException as exc:
                failure = exc
            partial.unlink(missing_ok=True)
            LOGGER.warning("Model download attempt %d/%d failed: %s", attempt, self.DOWNLOAD_ATTEMPTS, failure)
            if attempt < self.DOWNLOAD_ATTEMPTS:
                time.sleep(2 ** (attempt - 1))
        raise EmbeddingModelError(f"Could not download {self.MODEL_DOWNLOAD_URL}") from failure

    def _embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        encodings = [self._tokenizer.encode(text) for text in texts]
        input_ids = np.array([encoding.ids for encoding in encodings], dtype=np.int64)
        attention_mask = np.array([encoding.attention_mask for encoding in encodings], dtype=np.int64)
        hidden_state = self._session.run(
            None,
            {"input_ids": input_ids, "attention_mask": attention_mask, "token_type_ids": np.zeros_like(input_ids)},
        )[0]
        weights = attention_mask[..., np.newaxis]
        pooled = (hidden_state * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        norms = np.linalg.norm(pooled, axis=1)
        norms[norms == 0] = 1e-12
        return list((pooled / norms[:, np.newaxis]).astype(np.float32))


class EventEmbedder:
    """The single place that turns an event message into an embedding: sanitize (strip
    run-specific noise) then embed with BGE-small-en. Shared by the event processor and
    the eval's similarity dedup so both produce identical vectors from identical inputs."""

    def __init__(self):
        self.sanitizer = MessageSanitizer()
        self.model = BgeSmallEnEmbeddingModel()

    def embed(self, message: str) -> np.ndarray:
        sanitized = self.sanitizer.sanitize(message)
        if not sanitized or not sanitized.strip():
            raise ValueError("Sanitized message is empty")
        vectors = self.model([sanitized])
        if not vectors:
            raise ValueError("Embedding generation returned empty result")
        return vectors[0]

    def embed_many(self, messages: list[str]) -> list[np.ndarray]:
        sanitized = [self.sanitizer.sanitize(m) for m in messages]
        return self.model(sanitized)
