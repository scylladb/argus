from uuid import UUID

from flask import Blueprint, request

from argus.backend.models.web import ArgusUserView
from argus.backend.service.views_widgets.nemesis_stats import NemesisStatsService
from argus.backend.service.user import api_login_required


bp = Blueprint("nemesis_stats", __name__, url_prefix="/widgets")


@bp.route("/nemesis_data", methods=["GET"])
@api_login_required
def get_nemesis_data():
    view_id = UUID(request.args.get("view_id"))
    view: ArgusUserView = ArgusUserView.get(id=view_id)
    service = NemesisStatsService()
    nemesis_data = []
    for test_id in view.tests:
        data = service.get_nemesis_data(test_id)
        nemesis_data.extend(data)
    return {
        "status": "ok",
        "response": {"nemesis_data": nemesis_data},
    }
