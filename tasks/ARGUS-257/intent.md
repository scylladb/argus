# ARGUS-257 — SCT event similarity and summaries depend on a separate service

## Problem

Argus stores each SCT event when the client submits it, but the event's
embedding, its duplicate mark and its summary come later, from the ArgusAI
event similarity processor. That processor runs as its own service next to
the Argus backend. It polls the queue of unprocessed ERROR and CRITICAL
events, embeds each one, marks duplicates within the run, stores the
embedding, and starts the summary of each unique event.

Each Argus deployment has to install, configure and monitor this second
service. When it stops, events keep arriving, but they get no embedding, no
duplicate mark and no summary, and nothing in the backend shows the gap.

The processor code lives in `argusAI/`, outside the SCT plugin that owns the
events, the queue and the summary column it writes.

## Who it affects

- Users of the SCT run view: the similar events, the duplicate marks and the
  event summaries stop updating while the service is down.
- The SCT pipelines that submit events: their ERROR and CRITICAL events lose
  similarity and summary data for as long as the outage lasts.
- Whoever deploys and operates Argus: one more unit to install, configure and
  watch on the production and staging hosts.

## Evidence

Jira issue ARGUS-257:

```
Argus runs the ArgusAI event similarity processor as a separate service next to the Argus backend. This service creates the event embeddings, finds similar events, and starts the event summaries after Argus ingests the events. Each Argus deployment must install, configure, and monitor this second service. When the service stops, Argus gets no new similarity data and no new summaries. ARGUS-228 shows this failure: the service did not start because of a missing module, and nothing in the backend showed the problem.
```

Jira issue ARGUS-228, the journal on argus-staging:

```
Sep 11 10:07:44 argus-staging systemd[1]: Started argusai_event_similarity_processor_v2.service - Event Similarity Processor Service for Argus AI v2.
Sep 11 10:07:45 argus-staging uv[1996530]: Traceback (most recent call last):
Sep 11 10:07:45 argus-staging uv[1996530]:   File "/home/argus/app/argusAI/event_similarity_processor_v2.py", line 27, in <module>
Sep 11 10:07:45 argus-staging uv[1996530]:     from argus.backend.models.argus_ai import SCTCriticalEventEmbedding, SCTErrorEventEmbedding
Sep 11 10:07:45 argus-staging uv[1996530]:   File "/home/argus/app/argus/backend/models/argus_ai.py", line 6, in <module>
Sep 11 10:07:45 argus-staging uv[1996530]:     from coodie import ClusteringKey, Frozen, PrimaryKey, Static, Vector, VectorIndex
Sep 11 10:07:45 argus-staging uv[1996530]: ModuleNotFoundError: No module named 'coodie'
```

```
The service restarts on failure and hits the start limit, so it stays down.
```

```
No SCT event embeddings are produced while the service is down. Event similarity and deduplication in Argus have no new data.
```

## What good looks like

- A new ERROR or CRITICAL SCT event that Argus ingests gets its embedding,
  its duplicate mark and its summary without the ArgusAI service.
- Duplicate detection gives the same results for new events as before.
- Submitting events succeeds, and is not noticeably slower, when embedding,
  similarity search or summarization fails or is slow.
- An event whose processing was interrupted is processed later instead of
  being lost.
- No ArgusAI service runs on the production and staging hosts, and the
  deployment does not install one.
- The docs describe the deployment without the ArgusAI service.

## Out of scope

- The embedding library change (ARGUS-238).
- Showing the summary in the web UI and the CLI (ARGUS-193, ARGUS-194).
- Embeddings and summaries for events stored before this change that never
  entered the queue.
