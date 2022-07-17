import logging
from flask import (
    Blueprint,
    g,
    request,
    Request,
)
from argus.backend.error_handlers import handle_api_exception
from argus.backend.service.notification_manager import NotificationManagerService
from argus.backend.controller.auth import login_required


def get_payload(client_request: Request):
    if not client_request.is_json:
        raise Exception(
            "Content-Type mismatch, expected application/json, got:", client_request.content_type)
    request_payload = client_request.get_json()

    return request_payload


bp = Blueprint('notifications', __name__, url_prefix='/notifications')
LOGGER = logging.getLogger(__name__)
bp.register_error_handler(Exception, handle_api_exception)


@bp.route("/get")
@login_required
def get_notification():
    notification_id = request.args.get("id")
    if not notification_id:
        raise Exception("No notification id provided")
    service = NotificationManagerService()
    notification = service.get_notificaton(
        receiver=g.user.id, notification_id=notification_id)
    return {
        "status": "ok",
        "response": notification.to_dict()
    }


@bp.route("/get_unread")
@login_required
def get_unread_count():
    service = NotificationManagerService()
    unread_count = service.get_unread_count(receiver=g.user.id)
    return {
        "status": "ok",
        "response": unread_count
    }


@bp.route("/summary")
@login_required
def get_summary():
    after = request.args.get("afterId")
    limit = request.args.get("limit")
    limit = int(limit) if limit else 20
    service = NotificationManagerService()
    notifications = service.get_notifications(
        receiver=g.user.id,
        limit=limit,
        after=after
    )
    return {
        "status": "ok",
        "response": [n.to_dict_short_summary() for n in notifications]
    }


@bp.route("/read", methods=["POST"])
@login_required
def read_notification():
    payload = get_payload(request)
    service = NotificationManagerService()
    status = service.read_notification(
        receiver=g.user.id, notification_id=payload["id"])

    return {
        "status": "ok",
        "response": status
    }
