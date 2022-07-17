import logging
from flask import (
    Blueprint,
    render_template,
)
from argus.backend.controller.admin_api import bp as admin_api_bp
from argus.backend.service.user import login_required, check_roles
from argus.backend.models.web import UserRoles

bp = Blueprint('admin', __name__, url_prefix='/admin')
bp.register_blueprint(admin_api_bp)
LOGGER = logging.getLogger(__name__)


@bp.route("/")
@bp.route("/<string:path>")
@check_roles(UserRoles.Admin)
@login_required
def index(path: str = "index"):
    return render_template("admin/index.html.j2", current_route=path)
