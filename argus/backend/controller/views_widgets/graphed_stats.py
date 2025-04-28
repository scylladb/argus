from uuid import UUID

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
