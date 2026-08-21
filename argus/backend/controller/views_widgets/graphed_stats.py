from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from argus.backend.models.web import ArgusUserView, User
from argus.backend.service.user import api_current_user
from argus.backend.service.views_widgets.graphed_stats import GraphedStatsService
from argus.backend.util.encoders import ArgusJSONResponse

router = APIRouter(prefix="/widgets")


class RunsDetailsRequest(BaseModel):
    run_ids: list[str]


@router.get("/graphed_stats", name="api.view_api.graphed_stats.get_graphed_stats")
def get_graphed_stats(view_id: UUID = Query(...), filters: str | None = Query(None),
                      user: User = Depends(api_current_user)):
    view: ArgusUserView = ArgusUserView.get(id=view_id)
    service = GraphedStatsService()
    response_data = {
        "test_runs": [],
        "nemesis_data": []
    }

    for test_id in view.tests:
        data = service.get_graphed_stats(test_id, filters)
        response_data["test_runs"].extend(data["test_runs"])
        response_data["nemesis_data"].extend(data["nemesis_data"])
    return ArgusJSONResponse({
        "status": "ok",
        "response": response_data
    })


@router.post("/runs_details", name="api.view_api.graphed_stats.get_runs_details")
def get_runs_details(payload: RunsDetailsRequest, user: User = Depends(api_current_user)):
    """Get detailed information for provided test runs including assignee and attached issues."""
    service = GraphedStatsService()
    result = service.get_runs_details(payload.run_ids)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })
