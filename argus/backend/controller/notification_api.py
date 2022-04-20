import logging
from uuid import UUID
from flask import (
    Blueprint,
    g,
    request,
    Request,
)
from flask.json import jsonify
from argus.backend.service.notification_manager import NotificationManagerService
from argus.backend.controller.auth import login_required


def get_payload(client_request: Request):
    if not client_request.is_json:
        raise Exception(
            "Content-Type mismatch, expected application/json, got:", client_request.content_type)
    request_payload = client_request.get_json()

    return request_payload


# pylint: disable=broad-except
bp = Blueprint('notifications', __name__, url_prefix='/notifications')
LOGGER = logging.getLogger(__name__)


@bp.route("/get")
@login_required
def get_notification():
    res = {
        "status": "ok"
    }
    try:
        notification_id = request.args.get("id")
        if not notification_id:
            raise Exception("No notification id provided")
        service = NotificationManagerService()
        notification = service.get_notificaton(receiver=g.user.id, notification_id=notification_id)
        res["response"] = notification.to_dict()
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/get_unread")
@login_required
def get_unread_count():
    res = {
        "status": "ok"
    }
    try:
        service = NotificationManagerService()
        unread_count = service.get_unread_count(receiver=g.user.id)
        res["response"] = unread_count
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/summary")
@login_required
def get_summary():
    res = {
        "status": "ok"
    }
    try:
        after = request.args.get("afterId")
        limit = request.args.get("limit")
        limit = int(limit) if limit else 20
        service = NotificationManagerService()
        notifications = service.get_notifications(receiver=g.user.id, limit=limit, after=after)
        res["response"] = [n.to_dict_short_summary() for n in notifications]
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)


@bp.route("/read", methods=["POST"])
@login_required
def read_notification():
    res = {
        "status": "ok"
    }
    try:
        payload = get_payload(request)
        service = NotificationManagerService()
        status = service.read_notification(receiver=g.user.id, notification_id=payload["id"])
        res["response"] = status
    except Exception as exc:
        LOGGER.error("Exception in %s", request.endpoint, exc_info=True)
        res["status"] = "error"
        res["response"] = {
            "exception": exc.__class__.__name__,
            "arguments": exc.args
        }
    return jsonify(res)
