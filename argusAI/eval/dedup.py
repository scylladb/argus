"""Semantic (embedding) deduplication for the eval, mirroring the production worker.

The harness's default collection dedups by exact message string, but production
(event_similarity_processor_v2) dedups by *similarity*: it embeds the sanitized message
with BGE-small-en and treats two events as the same when their cosine distance is < 0.05
(i.e. > 0.95 similarity). This module runs that same pipeline — via the shared
``EventEmbedder`` the worker uses — over a collected set, so the eval measures the true
canonical set production would summarize.

Collapsed events are merged into the canonical's ``repeats`` count (as production folds
duplicates under the canonical), and only canonicals are returned.
"""

from __future__ import annotations

import logging

from chromadb.utils.distance_functions import cosine
from numpy import array

from argusAI.utils.embedding import EventEmbedder

from .events_source import EventSample

LOGGER = logging.getLogger(__name__)

# Production's duplicate threshold (event_similarity_processor_v2.py): cosine distance
# below this means "same event". Distance is 1 - cosine similarity, so 0.05 ≈ 95% similar.
DEFAULT_DISTANCE_THRESHOLD = 0.05


def deduplicate_by_similarity(
    events: list[EventSample], threshold: float = DEFAULT_DISTANCE_THRESHOLD
) -> list[EventSample]:
    """Collapse semantically-similar events into their first-seen canonical, using the same
    sanitize→embed pipeline as the worker. Returns only the canonicals, each with absorbed
    duplicates added to its ``repeats``."""
    if len(events) < 2:
        return events

    embeddings = [array(v, dtype=float) for v in EventEmbedder(write_log=False).embed_many([e.message for e in events])]

    canonicals: list[int] = []  # indices of kept events
    collapsed = 0
    for i, emb in enumerate(embeddings):
        match = next((c for c in canonicals if cosine(emb, embeddings[c]) < threshold), None)
        if match is None:
            canonicals.append(i)
        else:
            events[match].repeats += 1 + events[i].repeats
            collapsed += 1

    LOGGER.info(
        "Similarity dedup: %d events -> %d canonical (collapsed %d near-duplicates, threshold %.3f)",
        len(events),
        len(canonicals),
        collapsed,
        threshold,
    )
    return [events[c] for c in canonicals]
