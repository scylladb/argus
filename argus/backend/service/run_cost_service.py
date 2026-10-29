import asyncio
import logging
import math
from uuid import UUID

from cassandra import DriverException
from cassandra.cluster import NoHostAvailable
from coodie.cql_builder import build_update, parse_filter_kwargs, parse_update_kwargs
from coodie.aio import AsyncBatchQuery
from pydantic import BaseModel, Field

from argus.backend.error_handlers import DataValidationError
from argus.backend.models.run_cost import RunCost
from argus.backend.models.run_cost_rollup import RunCostRollup
from argus.backend.plugins.core import PluginModelBase
from argus.backend.plugins.loader import AVAILABLE_PLUGINS
from argus.backend.service.cost_rollup_service import CostRollupService

LOGGER = logging.getLogger(__name__)


class EstimatedCostRequest(BaseModel):
    value: float = Field(ge=0, allow_inf_nan=False)


class CostItemRequest(BaseModel):
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    cost: float = Field(ge=0, allow_inf_nan=False)
    pricing_tier: str | None = None
    leaked: bool = False


class CostItemsRequest(BaseModel):
    items: list[CostItemRequest]


class RunCostService:
    @classmethod
    async def _read_partition(cls, run_id: UUID) -> list[RunCost]:
        return await RunCost.find(run_id=run_id).all()

    @staticmethod
    def _items(rows: list[RunCost]) -> list[RunCost]:
        return [row for row in rows if row.name]

    async def set_estimated_cost(self, run_id: UUID, value: float) -> dict:
        await RunCost.find(run_id=run_id).update(estimated_cost=value)
        await self.refresh_rollup_guarded(run_id)
        return {"run_id": str(run_id), "estimated_cost": value}

    async def submit_cost_items(self, run_id: UUID, items: list[CostItemRequest]) -> dict:
        names = [item.name for item in items]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise DataValidationError(f"Cost item names must be unique within one payload: {', '.join(duplicates)}")

        async with AsyncBatchQuery() as batch:
            for item in items:
                batch.add(*self._item_write(run_id, item))

        actual_cost = await self.recompute_actual_cost(run_id)
        await self.refresh_rollup_guarded(run_id)
        return {"run_id": str(run_id), "submitted": len(items), "actual_cost": actual_cost}

    @staticmethod
    def _item_write(run_id: UUID, item: CostItemRequest) -> tuple[str, list]:
        set_data, _ = parse_update_kwargs({
            "cost": item.cost,
            "category": item.category,
            "pricing_tier": item.pricing_tier,
            "leaked": item.leaked,
        })
        return build_update(
            RunCost._get_table(),
            RunCost._get_keyspace(),
            set_data,
            parse_filter_kwargs({"run_id": run_id, "name": item.name}),
        )

    async def recompute_actual_cost(self, run_id: UUID, use_estimate: bool = False) -> float | None:
        rows = await self._read_partition(run_id)
        if not rows:
            return None

        items = self._items(rows)
        if items:
            total = math.fsum(item.cost or 0.0 for item in items)
        elif use_estimate:
            total = rows[0].estimated_cost
            if total is None:
                return None
        else:
            return None

        await RunCost.find(run_id=run_id).update(actual_cost=total)
        return total

    async def get_run_cost(self, run_id: UUID) -> dict:
        rows = await self._read_partition(run_id)
        items = sorted(self._items(rows), key=lambda row: (row.category or "", row.name))

        by_category: dict[str, float] = {}
        for item in items:
            category = item.category or ""
            by_category[category] = by_category.get(category, 0.0) + (item.cost or 0.0)

        return {
            "estimated_cost": rows[0].estimated_cost if rows else None,
            "actual_cost": rows[0].actual_cost if rows else None,
            "items": [
                {
                    "name": item.name,
                    "category": item.category,
                    "cost": item.cost,
                    "pricing_tier": item.pricing_tier,
                    "leaked": item.leaked,
                }
                for item in items
            ],
            "by_category": by_category,
        }

    @staticmethod
    async def _find_run(run_id: UUID) -> PluginModelBase | None:
        found = await asyncio.gather(*(
            plugin.model.find(id=run_id).only(*plugin.model.cost_rollup_columns()).first()
            for plugin in AVAILABLE_PLUGINS.values()
        ))
        return next((run for run in found if run), None)

    async def refresh_rollup(self, run_id: UUID) -> RunCostRollup | None:
        run = await self._find_run(run_id)
        if run is None:
            LOGGER.debug("No run %s in any plugin, the cost rollup waits for the run", run_id)
            return None
        return await CostRollupService().refresh(run)

    async def relocate_rollup(self, run_id: UUID, old_release_id: UUID | None) -> RunCostRollup | None:
        run = await self._find_run(run_id)
        if run is None:
            LOGGER.debug("No run %s in any plugin, the cost rollup waits for the run", run_id)
            return None
        return await CostRollupService().relocate(run, old_release_id)

    async def refresh_rollup_guarded(self, run_id: UUID) -> None:
        await self._guarded(self.refresh_rollup(run_id), run_id)

    async def relocate_rollup_guarded(self, run_id: UUID, old_release_id: UUID | None) -> None:
        await self._guarded(self.relocate_rollup(run_id, old_release_id), run_id)

    @staticmethod
    async def _guarded(refresh, run_id: UUID) -> None:
        try:
            await refresh
        except (DriverException, NoHostAvailable):
            LOGGER.exception("Could not refresh the cost rollup of run %s, the run is stored", run_id)
