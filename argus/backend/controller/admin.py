import logging

from fastapi import APIRouter, Depends, Request

from argus.backend.controller import admin_api
from argus.backend.models.web import User, UserRoles
from argus.backend.rendering import templates
from argus.backend.service.user import ui_require_roles

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")
router.include_router(admin_api.router)


@router.get("/", name="admin.index")
@router.get("/{path}", name="admin.index")
def index(asgi_request: Request, path: str = "index",
          user: User = Depends(ui_require_roles(UserRoles.Admin))):
    return templates.TemplateResponse(asgi_request, "admin/index.html.j2", {"current_route": path})
