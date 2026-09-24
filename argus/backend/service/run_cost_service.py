import logging
import math
from uuid import UUID

from coodie.cql_builder import build_update, parse_filter_kwargs, parse_update_kwargs
from coodie.aio import AsyncBatchQuery
from pydantic import BaseModel, Field

from argus.backend.error_handlers import DataValidationError
from argus.backend.models.run_cost import RunCost

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
    @staticmethod
    def _run_id(run_id: UUID | str) -> UUID:
        return UUID(run_id) if isinstance(run_id, str) else run_id

    @classmethod
    async def _read_partition(cls, run_id: UUID) -> list[RunCost]:
        return await RunCost.find(run_id=cls._run_id(run_id)).all()

    @staticmethod
    def _items(rows: list[RunCost]) -> list[RunCost]:
        return [row for row in rows if row.name]

    async def set_estimated_cost(self, run_id: UUID, value: float) -> dict:
        run_id = self._run_id(run_id)
        await RunCost.find(run_id=run_id).update(estimated_cost=value)
        return {"run_id": str(run_id), "estimated_cost": value}

    async def submit_cost_items(self, run_id: UUID, items: list[CostItemRequest]) -> dict:
        run_id = self._run_id(run_id)
        names = [item.name for item in items]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise DataValidationError(f"Cost item names must be unique within one payload: {', '.join(duplicates)}")

        async with AsyncBatchQuery() as batch:
            for item in items:
                batch.add(*self._item_write(run_id, item))

        actual_cost = await self.recompute_actual_cost(run_id)
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
        run_id = self._run_id(run_id)
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
