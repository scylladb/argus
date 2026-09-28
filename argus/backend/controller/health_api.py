from fastapi import APIRouter, Depends, Request

from argus.backend.models.web import User
from argus.backend.service.health_service import HealthSummaryService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/health")


@router.get("/summary", name="api.health.get_summary")
async def get_summary(request: Request, user: User = Depends(api_current_user)):
    """Return the dependency health summary that the navigation bar shows."""
    summary = await HealthSummaryService(request.app.state.config).get_summary()
    return APIResponse({
        "status": "ok",
        "response": summary,
    })
