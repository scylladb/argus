import logging
from uuid import UUID
from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for, make_response
)
from argus.backend.controller.notifications import bp as notifications_bp
from argus.backend.service.argus_service import ArgusService
from argus.backend.models.web import WebFileStorage
from argus.backend.service.user import UserService, login_required

LOGGER = logging.getLogger(__name__)

bp = Blueprint('teams', __name__, url_prefix="/teams")

@bp.route("/")
@login_required
def index():
    return render_template("teams.html.j2")
