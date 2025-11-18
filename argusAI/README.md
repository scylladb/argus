# Event Similarity Processor V2

## Overview

This directory contains the Event Similarity Processor V2 — the new system that generates and stores embeddings for SCT events. It supersedes the legacy `event_similarity_processor.py` that worked with the deprecated `sct_run` table, but for now both systems are allowed to run in parallel (see "Co‑existence with V1").

## Architecture

The processor follows a clean, decoupled flow:

1. Event creation → SCT events are submitted via `SCTService.submit_event()`
2. Queue → ERROR and CRITICAL events are added to `sct_unprocessed_events`
3. Processing loop → `event_similarity_processor_v2.py` continuously reads from the queue
4. Embedding generation → Message is sanitized, then embedded via the BGE‑Small‑EN model
5. Storage → Embeddings are written into severity‑specific tables
6. Cleanup → Processed events are removed from the queue

## Database Tables

### sct_unprocessed_events
Tracks events that need embedding generation:
- `run_id` (UUID, partition key)
- `severity` (text, clustering key)
- `ts` (timestamp, clustering key)

### sct_error_event_embedding
Stores ERROR event embeddings (separate table for performance):
- `run_id` (UUID, partition key)
- `ts` (timestamp, clustering key)
- `embedding` (list<float>)

### sct_critical_event_embedding
Stores CRITICAL event embeddings (separate table for performance):
- `run_id` (UUID, partition key)
- `ts` (timestamp, clustering key)
- `embedding` (list<float>)

Note: Using separate tables for ERROR and CRITICAL events keeps similarity searches scoped to a single severity class and improves query performance by avoiding mixed‑severity comparisons.

## Running the Processor

### Standalone
```bash
cd argusAI
PYTHONPATH=.. uv run event_similarity_processor_v2.py
```

### As a Service
The processor runs in an infinite loop and every ~1s:
- Reads up to 100 unprocessed events per batch
- Routes embeddings to the table matching the event severity
- Handles errors gracefully (logs and continues)
- Can be stopped with Ctrl+C

## Key Features

### Severity‑specific storage
- ERROR → `sct_error_event_embedding`
- CRITICAL → `sct_critical_event_embedding`
- Faster similarity searches within the same severity

### Message sanitization
Uses `MessageSanitizer` from `argusAI/utils/event_message_sanitizer.py` to:
- Remove IPs, URLs, file paths
- Normalize timestamps and memory addresses
- Clean up stack traces and backtraces
- Remove redundant/noisy details

### Embedding model
`BgeSmallEnEmbeddingModel` (BGE‑Small‑EN‑v1.5):
- 384‑dimensional embeddings
- Optimized for semantic similarity search
- Same model family used by the legacy processor for consistency

### Error handling
- Event not found → logged and skipped
- Empty message → logged and skipped
- Sanitization failure → logged and removed from queue
- Embedding failure → logged and removed from queue
- Failures are removed from the queue to avoid infinite retries

## Testing

### Unit tests
```bash
PYTHONPATH=. uv run pytest argusAI
```

Covers initialization, single/batch processing, error handling, and shutdown behavior.

### Integration tests
```bash
uv run pytest argus/backend/tests/sct_events/test_event_embedding_integration.py -v
```

Covers the end‑to‑end flow from event creation to storage, proper routing to severity tables, verifying that non‑ERROR/CRITICAL events don’t create queue entries, multi‑event processing, and error recovery.

## Monitoring & Metrics

Logging:
- INFO: processing cycles, batch counts, startup/shutdown, table routing
- DEBUG: per‑event processing, chosen table names
- WARNING: missing events, empty messages
- ERROR: processing/database failures

Metrics:
- `processed_count`: total successfully processed events
- `error_count`: total errors encountered

## Differences from V1

Improvements in V2:
1. Cleaner architecture: no Vector DB dependency for processing
2. Better error handling: failures don’t block processing
3. Simpler flow: queue → process → store
4. Severity‑specific tables for similarity performance
5. Comprehensive unit and integration tests

What’s not included in V2:
- Similarity search (removed from the processor itself)
- ChromaDB collections (not required for embedding storage)
- Historical event backfill (processes only new events)

## Performance Benefits

By separating ERROR and CRITICAL embeddings:
- Faster similarity searches (smaller, severity‑scoped sets)
- Better data locality
- Reduced query complexity (no severity filters inside similarity search)
- Improved scalability (per‑table tuning)

## Configuration

No dedicated config file is required for the processor itself. It uses the standard Argus configuration for database connectivity (e.g., ScyllaDB settings from your environment or YAML config such as `argus.yaml`/`argus.local.yaml`, depending on your deployment). The embedding model is auto‑downloaded to `~/.cache/chroma/onnx_models/`.

## Co‑existence with V1 (temporary)

- For now, both V1 (`event_similarity_processor.py`) and V2 (`event_similarity_processor_v2.py`) may run in parallel.
- There is no data migration at this time; V1 will be disabled once the team fully moves to V2.
- If you still need to run V1 locally for comparison or fallback:
  ```bash
  cd argusAI
  PYTHONPATH=.. uv run event_similarity_processor.py
  ```

## Notes

- Avoid mixing severities in similarity queries; use the dedicated tables for the best performance.
- If you encounter repeated failures for the same event, verify the event content after sanitization and check connectivity to the database and model files.
