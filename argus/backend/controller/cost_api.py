from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from argus.backend.models.web import User
from argus.backend.service.cost_explorer_service import CostExplorerService, CostQuery
from argus.backend.service.cost_rollup_service import as_utc
from argus.backend.service.run_cost_service import RunCostService
from argus.backend.service.user import api_current_user
from argus.backend.util.common import NoneIfEmpty
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/cost")
DEFAULT_WINDOW_DAYS = 90


def default_window(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    end = as_utc(end).astimezone(UTC) if end else datetime.now(UTC)
    if start:
        start = as_utc(start).astimezone(UTC)
    else:
        start = (end - timedelta(days=DEFAULT_WINDOW_DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, end


@router.get("/run/{run_id}", name="api.cost_api.get_run_cost")
async def get_run_cost(run_id: UUID, user: User = Depends(api_current_user)):
    result = await RunCostService().get_run_cost(run_id)
    return APIResponse({
        "status": "ok",
        "response": result
    })


@router.get("/explorer", name="api.cost_api.explorer")
async def explorer(start: Annotated[datetime | None, NoneIfEmpty, Query(alias="from")] = None,
                   end: Annotated[datetime | None, NoneIfEmpty, Query(alias="to")] = None,
                   release_names: list[str] = Query(default=[], alias="releaseName"),
                   group_ids: list[UUID] = Query(default=[], alias="groupId"),
                   test_ids: list[UUID] = Query(default=[], alias="testId"),
                   view_id: Annotated[UUID | None, NoneIfEmpty, Query(alias="viewId")] = None,
                   backends: list[str] = Query(default=[], alias="backend"),
                   plugins: list[str] = Query(default=[], alias="plugin"),
                   statuses: list[str] = Query(default=[], alias="status"),
                   tiers: list[Literal["spot", "on-demand"]] = Query(default=[], alias="tier"),
                   breakdown: Literal["group", "test"] = Query("group"),
                   granularity: Literal["day", "week", "month"] = Query("week"),
                   user: User = Depends(api_current_user)):
    start, end = default_window(start, end)
    service = CostExplorerService()
    window = {"start": start, "end": end, "release_ids": await service.release_ids_for(release_names),
              "group_ids": frozenset(group_ids), "test_ids": frozenset(test_ids), "backends": frozenset(backends),
              "plugins": frozenset(plugins), "statuses": frozenset(statuses), "tiers": frozenset(tiers),
              "breakdown": breakdown,
              "granularity": granularity}
    query = await service.query_for_view(view_id, **window) if view_id else CostQuery(**window)
    result = await service.explore(query)
    return APIResponse({
        "status": "ok",
        "response": result
    })
