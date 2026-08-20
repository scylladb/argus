from fastapi import APIRouter, Depends, Request

from argus.backend.models.web import User
from argus.backend.rendering import templates
from argus.backend.service.user import ui_current_user

router = APIRouter(prefix="/notifications")


@router.get("/", name="main.notifications.index")
def index(asgi_request: Request, user: User = Depends(ui_current_user)):
    return templates.TemplateResponse(asgi_request, "profile_notifications.html.j2")
