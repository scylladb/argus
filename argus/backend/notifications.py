from flask import (
    Blueprint,
    render_template,
)
from argus.backend.auth import login_required

# pylint: disable=broad-except
bp = Blueprint('notifications', __name__, url_prefix='/notifications')


@bp.route("/")
@login_required
def index():
    return render_template("profile_notifications.html.j2")
