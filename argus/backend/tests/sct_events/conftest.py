from threading import Event
from typing import Generator
from unittest.mock import patch

import pytest


class _StubEmbeddingModel:
    """Lightweight embedding stub to avoid network calls in tests."""

    def __call__(self, texts):
        return [[0.0] * 384 for _ in texts]


@pytest.fixture(scope="session", autouse=True)
def _patch_embedding_model() -> Generator[None, None, None]:
    """Replace the ONNX-based embedding model with a fast local stub."""

    with patch("argusAI.event_similarity_processor_v2.BgeSmallEnEmbeddingModel", return_value=_StubEmbeddingModel()):
        yield


@pytest.fixture(scope="session")
def event_similarity_processor() -> Generator["EventSimilarityProcessorV2", None, None]:
    from argusAI.event_similarity_processor_v2 import EventSimilarityProcessorV2

    processor = EventSimilarityProcessorV2(stop_event=Event())
    try:
        yield processor
    finally:
        processor.shutdown()


@pytest.fixture()
def embedding_processor(event_similarity_processor):
    processor = event_similarity_processor
    processor.stop_event.clear()
    processor.processed_count = 0
    processor.error_count = 0
    return processor
