# ARGUS-238 — argusAI depends on chromadb for an embedder and a distance function

## Problem

The V2 similarity worker stores and compares event embeddings in ScyllaDB. It
uses no vector database. The `ai` and `ai-eval` extras still install
chromadb, and through it grpc, kubernetes, opentelemetry, typer, bcrypt and
the rest of a vector database server, for three things:

- `BgeSmallEnEmbeddingModel` in `argusAI/utils/embedding.py` subclasses
  chromadb's `ONNXMiniLM_L6_V2` for the model download, the tokenization and
  the ONNX inference.
- `event_similarity_processor_v2.py` and `argusAI/eval/dedup.py` import
  `cosine` from `chromadb.utils.distance_functions`.
- The legacy V1 processor `argusAI/event_similarity_processor.py` keeps an
  in-memory ChromaDB collection. V2 supersedes it, and nothing runs it.

Every install of the worker, every CI run of the `ai` extra and the release
bundle carry that tree. The README still describes V1 as running beside V2.

## Who it affects

- The argusAI worker (`argus-ai-worker.service`, deployed from the release
  bundle by `roles/argus` in scylladb/qatools).
- The release bundle build, which imports `chromadb` in its self-check.
- Developers and CI who sync the `ai` or `ai-eval` extra.
- The eval harness, whose similarity dedup needs the `ai-eval` extra.

## Evidence

From the Jira issue:

```
ChromaDB is still a dependency of the ai and ai-eval extras, but only for three things:
BgeSmallEnEmbeddingModel in argusAI/utils/embedding.py subclasses chromadb's ONNXMiniLM_L6_V2 for model download, tokenization and ONNX inference.
event_similarity_processor_v2.py and argusAI/eval/dedup.py import cosine from chromadb.utils.distance_functions.
The legacy V1 processor argusAI/event_similarity_processor.py uses an in-memory ChromaDB collection. V2 supersedes it.
```

The chromadb imports in the tree:

```
argusAI/utils/embedding.py:4:from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
argusAI/event_similarity_processor_v2.py:24:from chromadb.utils.distance_functions import cosine
argusAI/eval/dedup.py:18:from chromadb.utils.distance_functions import cosine
argusAI/event_similarity_processor.py:6:import chromadb
scripts/release/build-bundle.sh:243:import cassandra, coodie, chromadb, gunicorn, uvicorn
```

The dependencies of `chromadb 1.5.9` in `uv.lock` include `grpcio`,
`kubernetes`, `opentelemetry-api`, `opentelemetry-exporter-otlp-proto-grpc`,
`opentelemetry-sdk`, `bcrypt`, `mmh3`, `pypika`, `typer`, `uvicorn[standard]`,
`onnxruntime` and `tokenizers`. The worker uses only the last two.

## What good looks like

- `uv sync --extra ai` does not install chromadb, and `git grep -i chroma`
  finds only the model cache path and the historical task records.
- The worker produces the same vectors for the same messages as before, so
  the embeddings already stored in ScyllaDB stay valid with no re-embedding.
- The V2 worker and the eval dedup find the same duplicates as before.
- The V1 processor and its README text are gone, and no host runs the V1
  unit.

## Out of scope

- Changing the model, the pooling or the duplicate threshold. Any of these
  would invalidate the stored vectors.
- Moving the model cache directory. The deployed host already holds the
  extracted model under `.cache/chroma`.
- The summarization worker and the eval scoring.
- Editing the historical records under `tasks/` and `docs/plans/archive/`.
