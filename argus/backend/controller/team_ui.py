import logging

from fastapi import APIRouter, Depends, Request

from argus.backend.models.web import User
from argus.backend.rendering import templates
from argus.backend.service.user import ui_current_user

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/teams")


@router.get("/", name="main.teams.index")
def index(asgi_request: Request, user: User = Depends(ui_current_user)):
    return templates.TemplateResponse(asgi_request, "teams.html.j2")
