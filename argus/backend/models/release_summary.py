import logging
from datetime import UTC, datetime
from typing import Annotated, Optional
from uuid import UUID

from coodie import ClusteringKey, PrimaryKey, Static
from coodie.aio import Document

LOGGER = logging.getLogger(__name__)
ROLLUP_VERSION = ""


class ReleaseSummary(Document):
    release_id: Annotated[UUID, PrimaryKey()]
    family: Annotated[str, ClusteringKey(clustering_key_index=0)]
    version: Annotated[str, ClusteringKey(clustering_key_index=1)]
    invalidated_at: Annotated[Optional[datetime], Static()] = None
    generated_at: Annotated[Optional[datetime], Static()] = None
    payload: Optional[str] = None

    class Settings:
        name = "release_summary_v1"


async def mark_release_summary_stale(*release_ids: UUID | None) -> None:
    now = datetime.now(UTC)
    for release_id in {release_id for release_id in release_ids if release_id}:
        try:
            await ReleaseSummary.find(release_id=release_id).update(invalidated_at=now)
        except Exception:  # noqa: BLE001 - a summary mark must never fail the client write that caused it
            LOGGER.warning("Failed to mark the release summary of %s stale", release_id, exc_info=True)
