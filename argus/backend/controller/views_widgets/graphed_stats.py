from uuid import UUID

from argus.backend.util.common import get_payload
from flask import Blueprint, request

from argus.backend.models.web import ArgusUserView
from argus.backend.service.views_widgets.graphed_stats import GraphedStatsService
from argus.backend.service.user import api_login_required

bp = Blueprint("graphed_stats", __name__, url_prefix="/widgets")


@bp.route("/graphed_stats", methods=["GET"])
@api_login_required
def get_graphed_stats():
    view_id = UUID(request.args.get("view_id"))
    view: ArgusUserView = ArgusUserView.get(id=view_id)
    service = GraphedStatsService()
    response_data = {
        "test_runs": [],
        "nemesis_data": []
    }

    filters = request.args.get("filters")

    for test_id in view.tests:
        data = service.get_graphed_stats(test_id, filters)
        response_data["test_runs"].extend(data["test_runs"])
        response_data["nemesis_data"].extend(data["nemesis_data"])
    return {
        "status": "ok",
        "response": response_data
    }


@bp.route("/runs_details", methods=["POST"])
@api_login_required
def get_runs_details():
    """Get detailed information for provided test runs including assignee and attached issues."""
    data = get_payload(request)
    if not data or "run_ids" not in data:
        raise ValueError("Missing run_ids parameter")

    run_ids = data["run_ids"]
    if not isinstance(run_ids, list):
        raise ValueError("run_ids must be a list")

    service = GraphedStatsService()
    result = service.get_runs_details(run_ids)

    return {
        "status": "ok",
        "response": result
    }
