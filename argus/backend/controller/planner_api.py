import logging
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel

from argus.backend.models.web import User
from argus.backend.service.planner_service import CopyPlanPayload, PlanningService
from argus.backend.service.test_lookup import TestLookup
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import ArgusJSONResponse

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/planning")


class ChangePlanOwnerRequest(BaseModel):
    newOwner: str


@router.get("/", name="api.planning_api.version")
def version(user: User = Depends(api_current_user)):
    result = PlanningService().version()

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/plan/{plan_id}/copy/check", name="api.planning_api.is_plan_eligible_for_copy")
def is_plan_eligible_for_copy(plan_id: UUID, release_id: UUID = Query(..., alias="releaseId"),
                              user: User = Depends(api_current_user)):
    result = PlanningService().check_plan_copy_eligibility(plan_id=plan_id, target_release_id=release_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/release/{release_id}/gridview", name="api.planning_api.grid_view_for_release")
def grid_view_for_release(release_id: UUID, user: User = Depends(api_current_user)):
    result = PlanningService().get_gridview_for_release(release_id=release_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/search", name="api.planning_api.search_tests")
def search_tests(query: str | None = Query(None), release_id: str | None = Query(None, alias="releaseId"),
                 user: User = Depends(api_current_user)):
    if query:
        res = TestLookup.test_lookup(query, release_id=release_id)
    else:
        res = []
    return ArgusJSONResponse({
        "status": "ok",
        "response": {
            "hits": res,
            "total": len(res)
        }
    })


@router.get("/group/{group_id}/explode", name="api.planning_api.explode_group")
def explode_group(group_id: str, user: User = Depends(api_current_user)):
    res = TestLookup.explode_group(group_id=group_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": res
    })


@router.get("/plan/{plan_id}/get", name="api.planning_api.get_plan")
def get_plan(plan_id: str, user: User = Depends(api_current_user)):
    result = PlanningService().get_plan(plan_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/release/{release_id}/all", name="api.planning_api.get_plans_for_release")
def get_plans_for_release(release_id: str, user: User = Depends(api_current_user)):
    result = PlanningService().get_plans_for_release(release_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/plan/create", name="api.planning_api.create_plan")
def create_plan(payload: dict = Body(...), user: User = Depends(api_current_user)):
    result = PlanningService().create_plan(payload, user)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/plan/update", name="api.planning_api.update_plan")
def update_plan(payload: dict = Body(...), user: User = Depends(api_current_user)):
    result = PlanningService().update_plan(payload, user)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/plan/copy", name="api.planning_api.copy_plan")
def copy_plan(payload: CopyPlanPayload, user: User = Depends(api_current_user)):
    result = PlanningService().copy_plan(payload, user)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.delete("/plan/{plan_id}/delete", name="api.planning_api.delete_plan")
def delete_plan(plan_id: str, delete_view: bool = Query(False, alias="deleteView"),
                user: User = Depends(api_current_user)):
    result = PlanningService().delete_plan(plan_id, delete_view=delete_view)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.post("/plan/{plan_id}/owner/set", name="api.planning_api.change_plan_owner")
def change_plan_owner(plan_id: str, payload: ChangePlanOwnerRequest,
                      user: User = Depends(api_current_user)):
    result = PlanningService().change_plan_owner(plan_id=plan_id, new_owner=payload.newOwner)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result
    })


@router.get("/plan/{plan_id}/resolve_entities", name="api.planning_api.resolve_plan_entities")
def resolve_plan_entities(plan_id: str, user: User = Depends(api_current_user)):
    service = PlanningService()
    result = service.resolve_plan(plan_id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result,
    })


@router.post("/plan/trigger", name="api.planning_api.trigger_jobs_for_plans")
def trigger_jobs_for_plans(payload: dict = Body(...), user: User = Depends(api_current_user)):
    service = PlanningService()
    result = service.trigger_jobs(payload, user.username)

    return ArgusJSONResponse({
        "status": "ok",
        "response": result,
    })
