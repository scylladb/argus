import logging

from fastapi import APIRouter, Depends, Request
from flask import Blueprint

from argus.backend.controller import admin_api
from argus.backend.models.web import User, UserRoles
from argus.backend.rendering import render_template
from argus.backend.service.user import ui_require_roles

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")
router.include_router(admin_api.router)


@router.get("/", name="admin.index")
@router.get("/{path}", name="admin.index")
def index(asgi_request: Request, path: str = "index",
          user: User = Depends(ui_require_roles(UserRoles.Admin))):
    return render_template(asgi_request, "admin/index.html.j2", current_route=path)


# The routes above are served by FastAPI; these view-less rules keep the
# endpoints buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint('admin', __name__, url_prefix='/admin')
bp.register_blueprint(admin_api.bp)
bp.add_url_rule("/", "index", None)
bp.add_url_rule("/<string:path>", "index", None)
