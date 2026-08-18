import logging

from fastapi import APIRouter, Depends, Request
from flask import Blueprint

from argus.backend.models.web import User
from argus.backend.rendering import render_template
from argus.backend.service.user import ui_current_user

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/teams")


@router.get("/", name="main.teams.index")
def index(asgi_request: Request, user: User = Depends(ui_current_user)):
    return render_template(asgi_request, "teams.html.j2")


# The route above is served by FastAPI; this view-less rule keeps the
# endpoint buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint('teams', __name__, url_prefix="/teams")
bp.add_url_rule("/", "index", None)
