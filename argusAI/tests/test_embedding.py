"""Unit tests for the BGE-small-en embedder and the cosine distance.

The tokenizer and the ONNX session are fakes and the S3 download is served by requests_mock, so
no model is needed on disk.
"""

import hashlib
import io
import tarfile

import numpy as np
import pytest
import requests

from argusAI.utils import embedding
from argusAI.utils.embedding import BgeSmallEnEmbeddingModel, EmbeddingModelError, cosine

SEQUENCE_LENGTH = 4
# One row per token position. Positions 2 and 3 are padding in a two-word text and must not count.
HIDDEN_STATE = np.array([[3.0, 0.0], [0.0, 4.0], [100.0, 100.0], [100.0, 100.0]], dtype=np.float32)


class FakeEncoding:
    def __init__(self, attended: int):
        self.ids = [1] * attended + [0] * (SEQUENCE_LENGTH - attended)
        self.attention_mask = [1] * attended + [0] * (SEQUENCE_LENGTH - attended)


class FakeTokenizer:
    """One token per word, padded to SEQUENCE_LENGTH."""

    @classmethod
    def from_file(cls, path):
        return cls()

    def enable_truncation(self, max_length):
        pass

    def enable_padding(self, pad_id, pad_token, length):
        pass

    def encode(self, text):
        return FakeEncoding(min(len(text.split()), SEQUENCE_LENGTH))


class FakeSession:
    hidden_state = HIDDEN_STATE

    def __init__(self, path, sess_options=None, providers=None):
        pass

    def run(self, output_names, feeds):
        batch = feeds["input_ids"].shape[0]
        return [np.broadcast_to(self.hidden_state, (batch, *self.hidden_state.shape)).copy()]


def _archive_bytes() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name in ("onnx/model.onnx", "onnx/tokenizer.json"):
            info = tarfile.TarInfo(name)
            info.size = 0
            tar.addfile(info, io.BytesIO(b""))
    return buffer.getvalue()


@pytest.fixture
def model_dir(tmp_path, monkeypatch):
    path = tmp_path / "bge-small-en-v1.5"
    monkeypatch.setattr(BgeSmallEnEmbeddingModel, "DOWNLOAD_PATH", path)
    monkeypatch.setattr(embedding, "Tokenizer", FakeTokenizer)
    monkeypatch.setattr(embedding.ort, "InferenceSession", FakeSession)
    return path


@pytest.fixture
def extracted_model(model_dir):
    (model_dir / "onnx").mkdir(parents=True)
    (model_dir / "onnx" / "model.onnx").touch()
    (model_dir / "onnx" / "tokenizer.json").touch()
    return model_dir


@pytest.fixture
def archive(monkeypatch):
    content = _archive_bytes()
    monkeypatch.setattr(BgeSmallEnEmbeddingModel, "_MODEL_SHA256", hashlib.sha256(content).hexdigest())
    return content


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(embedding.time, "sleep", calls.append)
    return calls


def test_embeds_the_mean_of_attended_tokens_as_a_unit_vector(extracted_model, requests_mock):
    vectors = BgeSmallEnEmbeddingModel()(["two words", "one", "two words"])

    assert len(vectors) == 3
    np.testing.assert_allclose(vectors[0], [0.6, 0.8], rtol=1e-6)
    np.testing.assert_allclose(vectors[1], [1.0, 0.0], rtol=1e-6)
    assert all(vector.dtype == np.float32 for vector in vectors)


def test_embeds_a_zero_hidden_state_as_a_zero_vector(extracted_model, monkeypatch, requests_mock):
    monkeypatch.setattr(FakeSession, "hidden_state", np.zeros_like(HIDDEN_STATE))

    [vector] = BgeSmallEnEmbeddingModel()(["two words"])

    np.testing.assert_array_equal(vector, [0.0, 0.0])


def test_returns_no_vectors_for_no_texts(extracted_model, requests_mock):
    assert BgeSmallEnEmbeddingModel()([]) == []


def test_downloads_verifies_and_extracts_the_archive(model_dir, archive, requests_mock):
    requests_mock.get(BgeSmallEnEmbeddingModel.MODEL_DOWNLOAD_URL, content=archive)

    vectors = BgeSmallEnEmbeddingModel()(["two words"])

    assert len(vectors) == 1
    assert requests_mock.call_count == 1
    assert (model_dir / "onnx.tar.gz").read_bytes() == archive
    assert (model_dir / "onnx" / "model.onnx").exists()
    assert (model_dir / "onnx" / "tokenizer.json").exists()


def test_reuses_the_extracted_model_without_a_request(extracted_model, requests_mock):
    BgeSmallEnEmbeddingModel()(["two words"])

    assert requests_mock.call_count == 0


def test_extracts_a_cached_archive_without_a_request(model_dir, archive, requests_mock):
    model_dir.mkdir()
    (model_dir / "onnx.tar.gz").write_bytes(archive)

    BgeSmallEnEmbeddingModel()(["two words"])

    assert requests_mock.call_count == 0
    assert (model_dir / "onnx" / "model.onnx").exists()


def test_raises_after_three_mismatched_downloads_and_removes_the_file(model_dir, archive, requests_mock, sleeps):
    requests_mock.get(BgeSmallEnEmbeddingModel.MODEL_DOWNLOAD_URL, content=b"not the model")

    with pytest.raises(EmbeddingModelError):
        BgeSmallEnEmbeddingModel()(["two words"])

    assert requests_mock.call_count == 3
    assert sleeps == [1, 2]
    assert not (model_dir / "onnx.tar.gz").exists()


def test_retries_a_failed_request_then_succeeds(model_dir, archive, requests_mock, sleeps):
    requests_mock.get(
        BgeSmallEnEmbeddingModel.MODEL_DOWNLOAD_URL,
        [{"exc": requests.ConnectionError}, {"status_code": 503}, {"content": archive}],
    )

    vectors = BgeSmallEnEmbeddingModel()(["two words"])

    assert len(vectors) == 1
    assert requests_mock.call_count == 3
    assert sleeps == [1, 2]


def test_cosine_is_zero_for_parallel_and_one_for_orthogonal_vectors():
    assert cosine(np.array([1.0, 2.0]), np.array([2.0, 4.0])) == pytest.approx(0.0, abs=1e-12)
    assert cosine(np.array([1.0, 0.0]), np.array([0.0, 3.0])) == pytest.approx(1.0)
