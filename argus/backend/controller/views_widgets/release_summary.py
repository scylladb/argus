from uuid import UUID

from fastapi import APIRouter, Depends, Query

from argus.backend.models.web import User
from argus.backend.service.release_summary import ReleaseSummaryService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/widgets")


@router.get("/release_summary", name="api.view_api.release_summary.get_release_summary")
async def get_release_summary(view_id: UUID = Query(...), user: User = Depends(api_current_user)):
    return APIResponse({
        "status": "ok",
        "response": await ReleaseSummaryService().get_for_view(view_id)
    })
