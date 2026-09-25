from uuid import UUID

from fastapi import APIRouter, Depends, Query

from argus.backend.models.web import ArgusUserView, User
from argus.backend.service.user import api_current_user
from argus.backend.service.views_widgets.nemesis_stats import NemesisStatsService
from argus.backend.util.common import gather_limited
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/widgets")


@router.get("/nemesis_data", name="api.view_api.nemesis_stats.get_nemesis_data")
async def get_nemesis_data(view_id: UUID = Query(...), user: User = Depends(api_current_user)):
    view: ArgusUserView = await ArgusUserView.get(id=view_id)
    service = NemesisStatsService()
    nemesis_data = []
    results = await gather_limited(service.get_nemesis_data(test_id) for test_id in view.tests)
    for data in results:
        nemesis_data.extend(data)
    return APIResponse({
        "status": "ok",
        "response": {"nemesis_data": nemesis_data},
    })
