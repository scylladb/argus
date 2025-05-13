import logging
from uuid import UUID
from flask import (
    Blueprint,
    request
)
from argus.backend.error_handlers import handle_api_exception
from argus.backend.service.planner_service import CopyPlanPayload, PlanningService, TempPlanPayload
from argus.backend.service.test_lookup import TestLookup
from argus.backend.service.user import api_login_required
from argus.backend.util.common import get_payload

bp = Blueprint('planning_api', __name__, url_prefix='/planning')
LOGGER = logging.getLogger(__name__)
bp.register_error_handler(Exception, handle_api_exception)


@bp.route("/", methods=["GET"])
@api_login_required
def version():

    result = PlanningService().version()

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/plan/<string:plan_id>/copy/check", methods=["GET"])
@api_login_required
def is_plan_eligible_for_copy(plan_id: str):
    release_id = request.args.get("releaseId")
    if not release_id:
        raise Exception("Missing release id.")

    result = PlanningService().check_plan_copy_eligibility(plan_id=UUID(plan_id), target_release_id=UUID(release_id))

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/release/<string:release_id>/gridview", methods=["GET"])
@api_login_required
def grid_view_for_release(release_id: str):

    result = PlanningService().get_gridview_for_release(release_id=UUID(release_id))

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/search", methods=["GET"])
@api_login_required
def search_tests():
    query = request.args.get("query")
    release_id = request.args.get('releaseId')
    service = TestLookup
    if query:
        res = service.test_lookup(query, release_id=release_id)
    else:
        res = []
    return {
        "status": "ok",
        "response": {
            "hits": res,
            "total": len(res)
        }
    }


@bp.route("/group/<string:group_id>/explode", methods=["GET"])
@api_login_required
def explode_group(group_id: str):
    service = TestLookup
    res = service.explode_group(group_id=group_id)
    return {
        "status": "ok",
        "response": res
    }


@bp.route("/plan/<string:plan_id>/get", methods=["GET"])
@api_login_required
def get_plan(plan_id: str):
    result = PlanningService().get_plan(plan_id)

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/release/<string:release_id>/all", methods=["GET"])
@api_login_required
def get_plans_for_release(release_id: str):
    result = PlanningService().get_plans_for_release(release_id)

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/plan/create", methods=["POST"])
@api_login_required
def create_plan():
    payload = get_payload(request)
    result = PlanningService().create_plan(payload)

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/plan/update", methods=["POST"])
@api_login_required
def update_plan():
    payload = get_payload(request)
    result = PlanningService().update_plan(payload)

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/plan/copy", methods=["POST"])
@api_login_required
def copy_plan():
    payload = get_payload(request)
    payload["plan"] = TempPlanPayload(**payload["plan"])
    result = PlanningService().copy_plan(CopyPlanPayload(**payload))

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/plan/<string:plan_id>/delete", methods=["DELETE"])
@api_login_required
def delete_plan(plan_id: str):
    result = PlanningService().delete_plan(plan_id)

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/plan/<string:plan_id>/owner/set", methods=["POST"])
@api_login_required
def change_plan_owner(plan_id: str):
    payload = get_payload(request)
    result = PlanningService().change_plan_owner(plan_id=plan_id, new_owner=payload["newOwner"])

    return {
        "status": "ok",
        "response": result
    }


@bp.route("/plan/<string:plan_id>/resolve_entities", methods=["GET"])
@api_login_required
def resolve_plan_entities(plan_id: str):

    service = PlanningService()
    result = service.resolve_plan(plan_id)

    return {
        "status": "ok",
        "response": result,
    }


@bp.route("/plan/trigger", methods=["POST"])
@api_login_required
def trigger_jobs_for_plans():

    payload = get_payload(request)
    service = PlanningService()
    result = service.trigger_jobs(payload)

    return {
        "status": "ok",
        "response": result,
    }
