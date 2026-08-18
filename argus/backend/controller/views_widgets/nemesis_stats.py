from uuid import UUID

from fastapi import APIRouter, Depends, Query
from flask import Blueprint

from argus.backend.models.web import ArgusUserView, User
from argus.backend.service.user import api_current_user
from argus.backend.service.views_widgets.nemesis_stats import NemesisStatsService
from argus.backend.util.encoders import ArgusJSONResponse

router = APIRouter(prefix="/widgets")


@router.get("/nemesis_data", name="api.view_api.nemesis_stats.get_nemesis_data")
def get_nemesis_data(view_id: UUID = Query(...), user: User = Depends(api_current_user)):
    view: ArgusUserView = ArgusUserView.get(id=view_id)
    service = NemesisStatsService()
    nemesis_data = []
    for test_id in view.tests:
        data = service.get_nemesis_data(test_id)
        nemesis_data.extend(data)
    return ArgusJSONResponse({
        "status": "ok",
        "response": {"nemesis_data": nemesis_data},
    })


# The route above is served by FastAPI; this view-less rule keeps the
# endpoint buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint("nemesis_stats", __name__, url_prefix="/widgets")
bp.add_url_rule("/nemesis_data", "get_nemesis_data", None)
