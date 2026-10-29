import logging
import math
from datetime import UTC, datetime
from uuid import UUID

from argus.backend.models.run_cost import RunCost
from coodie.exceptions import DocumentNotFound

from argus.backend.models.run_cost_rollup import UNASSIGNED_RELEASE, RunCostReleaseSpan, RunCostRollup
from argus.backend.plugins.core import PluginModelBase

LOGGER = logging.getLogger(__name__)
SPOT = "spot"
ON_DEMAND = "on-demand"
COVERAGE_COMPLETE = "complete"
COVERAGE_PARTIAL = "partial"
COVERAGE_NONE = "none"


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class CostRollupService:
    @staticmethod
    def month_of(start_time: datetime) -> str:
        return as_utc(start_time).strftime("%Y-%m")

    @staticmethod
    def coverage(resource_count: int | None, priced_count: int | None, item_count: int) -> str:
        if not item_count:
            return COVERAGE_NONE
        if not resource_count:
            return COVERAGE_COMPLETE
        return COVERAGE_COMPLETE if (priced_count or 0) >= resource_count else COVERAGE_PARTIAL

    @staticmethod
    def _tier_sums(items: list[RunCost]) -> dict[str, float | int]:
        groups = {
            "spot": [item for item in items if item.pricing_tier == SPOT],
            "on_demand": [item for item in items if item.pricing_tier == ON_DEMAND],
            "untiered": [item for item in items if item.pricing_tier not in (SPOT, ON_DEMAND)],
            "leaked": [item for item in items if item.leaked],
        }
        sums = {f"{name}_cost": math.fsum(item.cost or 0.0 for item in group) for name, group in groups.items()}
        counts = {f"{name}_count": len(group) for name, group in groups.items()}
        return sums | counts

    async def refresh(self, run: PluginModelBase) -> RunCostRollup:
        rows = await RunCost.find(run_id=run.id).all()
        items = [row for row in rows if row.name]
        fields = await run.cost_rollup_fields({item.name for item in items})
        end_time = run.end_time if run.end_time and run.end_time.timestamp() > 0 else None
        rollup = RunCostRollup(
            month=self.month_of(run.start_time),
            release_id=run.release_id or UNASSIGNED_RELEASE,
            start_time=as_utc(run.start_time),
            run_id=run.id,
            plugin_name=run._plugin_name,
            build_id=run.build_id,
            build_number=run.build_number,
            group_id=run.group_id,
            test_id=run.test_id,
            status=run.status,
            end_time=as_utc(end_time) if end_time else None,
            estimated_cost=rows[0].estimated_cost if rows else None,
            actual_cost=rows[0].actual_cost if rows else None,
            item_count=len(items),
            **self._tier_sums(items),
            **fields,
        )
        rollup.coverage = self.coverage(rollup.resource_count, rollup.priced_count, rollup.item_count)
        await rollup.save()
        await self.extend_span(rollup.release_id, rollup.start_time)
        return rollup

    async def relocate(self, run: PluginModelBase, old_release_id: UUID | None) -> RunCostRollup:
        old_key = old_release_id or UNASSIGNED_RELEASE
        if old_key != (run.release_id or UNASSIGNED_RELEASE):
            await RunCostRollup.find(month=self.month_of(run.start_time), release_id=old_key,
                                     start_time=as_utc(run.start_time), run_id=run.id).delete()
        return await self.refresh(run)

    @staticmethod
    async def extend_span(release_id: UUID, start_time: datetime) -> None:
        try:
            span = await RunCostReleaseSpan.get(release_id=release_id)
        except DocumentNotFound:
            await RunCostReleaseSpan(release_id=release_id, first_start=start_time, last_start=start_time).save()
            return
        changes = {}
        if start_time < as_utc(span.first_start):
            changes["first_start"] = start_time
        if start_time > as_utc(span.last_start):
            changes["last_start"] = start_time
        if changes:
            await RunCostReleaseSpan.find(release_id=release_id).update(**changes)
