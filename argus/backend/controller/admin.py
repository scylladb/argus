import logging
from uuid import UUID
from flask import (
    Blueprint,
    g,
    request,
    session,
    flash,
    redirect,
    render_template,
    url_for,
    make_response
)
from flask.json import jsonify
from argus.backend.service.argus_service import ArgusService
from argus.backend.service.admin import AdminService
from argus.backend.controller.admin_api import bp as admin_api_bp
from argus.backend.controller.auth import login_required, check_roles
from argus.db.models import UserRoles

# pylint: disable=broad-except
bp = Blueprint('admin', __name__, url_prefix='/admin')
bp.register_blueprint(admin_api_bp)
LOGGER = logging.getLogger(__name__)


@bp.route("/")
@bp.route("/<string:path>")
@check_roles(UserRoles.Admin)
@login_required
def index(path: str = "index"):
    return render_template("admin/index.html.j2", current_route=path)
