from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from argus.backend.models.web import ArgusUserView, User
from argus.backend.service.user import api_current_user
from argus.backend.service.views_widgets.graphed_stats import GraphedStatsService
from argus.backend.util.concurrency import map_concurrently
from argus.backend.util.encoders import APIResponse

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

    # One query per test (results are partitioned by test_id), so fan out
    # concurrently -- sequentially this endpoint costs the sum of the per-test
    # queries rather than roughly the slowest. Order is preserved.
    for data in map_concurrently(lambda test_id: service.get_graphed_stats(test_id, filters), view.tests):
        response_data["test_runs"].extend(data["test_runs"])
        response_data["nemesis_data"].extend(data["nemesis_data"])
    return APIResponse({
        "status": "ok",
        "response": response_data
    })


@router.post("/runs_details", name="api.view_api.graphed_stats.get_runs_details")
def get_runs_details(payload: RunsDetailsRequest, user: User = Depends(api_current_user)):
    """Get detailed information for provided test runs including assignee and attached issues."""
    service = GraphedStatsService()
    result = service.get_runs_details(payload.run_ids)

    return APIResponse({
        "status": "ok",
        "response": result
    })
