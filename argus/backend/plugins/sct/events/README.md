# SCT event processing

This package embeds SCT `ERROR` and `CRITICAL` events, marks the duplicates
within a run, and summarizes the unique ones. It runs inside the Argus backend.

## Flow

1. The SCT client submits events to `POST /api/v1/client/sct/{run_id}/event/submit`.
2. `SCTService.submit_events()` stores each event in `sct_event`. For an
   `ERROR` or `CRITICAL` event it also writes a row to `sct_unprocessed_events`
   with `queued_at` set.
3. The route answers, then runs `EventProcessor.process()` as a FastAPI
   background task in the same gunicorn worker.
4. For each event, in order and one run at a time per worker, the processor:
   - sanitizes the message (`sanitizer.py`) and embeds it with BGE-small-en
     (`embedding.py`), on a dedicated thread;
   - reads the embeddings already stored for the run and severity, and marks
     the event a duplicate (`sct_event.duplicate_id`) of the first stored one
     within cosine distance 0.05, newest first;
   - otherwise stores its embedding;
   - deletes the queue row.
5. The unique events go to `SummaryDispatcher`, which asks Claude for a
   summary and writes it to `sct_event.summary`.

A failure in the background task never reaches the client. An event whose
message is empty, or empty after sanitizing, leaves the queue without an
embedding. Any other failure leaves the queue row in place.

## Recovery sweep

```bash
uv run python -m argus.backend.cli process-event-queue [--min-age SECONDS]
```

The sweep processes the queue rows older than `--min-age`, 600 seconds by
default, and the rows that have no `queued_at`. A maintenance timer runs it on
the Argus hosts. A row is that old only when its background task did not
finish, for instance because the worker restarted.

## Tables

| Table | Key | Content |
|---|---|---|
| `sct_unprocessed_events` | `run_id`, `severity`, `ts` | `queued_at` |
| `sct_error_event_embedding` | `run_id`, `ts` | `embedding vector<float, 384>` |
| `sct_critical_event_embedding` | `run_id`, `ts` | `embedding vector<float, 384>` |

One embedding table per severity keeps a similarity search within its class.
Both carry a cosine vector index for the similar-events search across runs.

## Embedding model

`BgeSmallEnEmbeddingModel` runs BGE-small-en-v1.5 through `onnxruntime` and
`tokenizers`: 384 dimensions, mean pooling, unit length. Each gunicorn worker
loads it on first use from `~/.cache/chroma/onnx_models/bge-small-en-v1.5/`,
downloading and verifying the archive when it is missing. Download and
extraction publish their result with a rename, so workers that start at once
do not see each other's partial files.

## Summarization

Off unless `argus_web.yaml` sets `EVENT_SUMMARIZATION_ENABLED: true` and
`ANTHROPIC_API_KEY`. `argus_web.example.yaml` lists the other keys. The limits
on concurrency and backlog hold per gunicorn worker. The
`argus_event_summarization_*` series appear on the backend `/metrics`.

`eval/` holds the offline harness that picked the model and the prompt; see
`eval/README.md`.

## Tests

```bash
uv run pytest argus/backend/tests/sct_events
```

The backend test suite replaces the BGE model with a stub that maps equal
texts to equal unit vectors, so no model is downloaded.
