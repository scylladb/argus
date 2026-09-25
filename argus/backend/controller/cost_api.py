from uuid import UUID

from fastapi import APIRouter, Depends

from argus.backend.models.web import User
from argus.backend.service.run_cost_service import RunCostService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/cost")


@router.get("/run/{run_id}", name="api.cost_api.get_run_cost")
async def get_run_cost(run_id: UUID, user: User = Depends(api_current_user)):
    result = await RunCostService().get_run_cost(run_id)
    return APIResponse({
        "status": "ok",
        "response": result
    })
