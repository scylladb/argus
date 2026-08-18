import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from flask import Blueprint
from pydantic import BaseModel

from argus.backend.error_handlers import handle_api_exception
from argus.backend.models.web import User
from argus.backend.service.notification_manager import NotificationManagerService
from argus.backend.service.user import api_current_user
from argus.backend.util.encoders import ArgusJSONResponse

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications")


class ReadNotificationRequest(BaseModel):
    id: UUID


@router.get("/get", name="api.notifications.get_notification")
def get_notification(notification_id: UUID = Query(..., alias="id"),
                     user: User = Depends(api_current_user)):
    service = NotificationManagerService()
    notification = service.get_notificaton(
        receiver=user.id, notification_id=notification_id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": notification.to_dict()
    })


@router.get("/get_unread", name="api.notifications.get_unread_count")
def get_unread_count(user: User = Depends(api_current_user)):
    service = NotificationManagerService()
    unread_count = service.get_unread_count(receiver=user.id)
    return ArgusJSONResponse({
        "status": "ok",
        "response": unread_count
    })


@router.get("/summary", name="api.notifications.get_summary")
def get_summary(after: str | None = Query(None, alias="afterId"),
                limit: int = Query(20),
                user: User = Depends(api_current_user)):
    service = NotificationManagerService()
    notifications = service.get_notifications(
        receiver=user.id,
        limit=limit,
        after=after
    )
    return ArgusJSONResponse({
        "status": "ok",
        "response": [n.to_dict_short_summary() for n in notifications]
    })


@router.post("/read", name="api.notifications.read_notification")
def read_notification(payload: ReadNotificationRequest, user: User = Depends(api_current_user)):
    service = NotificationManagerService()
    status = service.read_notification(
        receiver=user.id, notification_id=payload.id)

    return ArgusJSONResponse({
        "status": "ok",
        "response": status
    })


# The routes above are served by FastAPI; these view-less rules keep the
# endpoints buildable through Flask's url_for until the Flask app is retired.
bp = Blueprint('notifications', __name__, url_prefix='/notifications')
bp.register_error_handler(Exception, handle_api_exception)
for _rule, _endpoint in (
    ("/get", "get_notification"),
    ("/get_unread", "get_unread_count"),
    ("/summary", "get_summary"),
    ("/read", "read_notification"),
):
    bp.add_url_rule(_rule, _endpoint, None)
