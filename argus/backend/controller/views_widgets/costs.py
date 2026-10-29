from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from argus.backend.models.web import User
from argus.backend.service.cost_explorer_service import CostExplorerService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/widgets")
MAX_WIDGET_DAYS = 365
DAILY_UP_TO = 31


@router.get("/costs", name="api.view_api.costs.get_costs")
async def get_costs(view_id: UUID = Query(...), days: int = Query(30, ge=1, le=MAX_WIDGET_DAYS),
                    user: User = Depends(api_current_user)):
    end = datetime.now(UTC)
    start = (end - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    service = CostExplorerService()
    query = await service.query_for_view(view_id, start=start, end=end,
                                         granularity="day" if days <= DAILY_UP_TO else "week")
    return APIResponse({
        "status": "ok",
        "response": await service.explore(query)
    })
