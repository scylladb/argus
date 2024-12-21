from dataclasses import asdict
from uuid import UUID

from flask import Blueprint, request, g

from argus.backend.service.user import api_login_required
from argus.backend.service.views_widgets.highlights import (
    HighlightCreate,
    HighlightsService,
    HighlightArchive,
    HighlightUpdate,
    HighlightSetAssignee,
    HighlightSetCompleted,
    CommentUpdate,
    CommentDelete,
    CommentCreate,
)
from argus.backend.util.common import get_payload

bp = Blueprint("view_widgets", __name__, url_prefix="/widgets")


@bp.route("/highlights/create", methods=["POST"])
@api_login_required
def create_highlight():
    creator_id = g.user.id
    payload = HighlightCreate(**get_payload(request))
    service = HighlightsService()
    highlight = service.create(creator_id, payload)
    return {"status": "ok", "response": asdict(highlight)}


@bp.route("/highlights", methods=["GET"])
@api_login_required
def get_highlights():
    view_id = UUID(request.args.get("view_id"))
    index = int(request.args.get("index"))
    service = HighlightsService()
    highlights, action_items = service.get_highlights(view_id, index)
    return {
        "status": "ok",
        "response": {
            "highlights": [asdict(h) for h in highlights],
            "action_items": [asdict(a) for a in action_items],
        },
    }


@bp.route("/highlights/archive", methods=["POST"])
@api_login_required
def archive_highlight():
    payload = HighlightArchive(**get_payload(request))
    service = HighlightsService()
    service.archive_highlight(payload)
    return {"status": "ok"}


@bp.route("/highlights/unarchive", methods=["POST"])
@api_login_required
def unarchive_highlight():
    payload = HighlightArchive(**get_payload(request))
    service = HighlightsService()
    service.unarchive_highlight(payload)
    return {"status": "ok"}


@bp.route("/highlights/update", methods=["POST"])
@api_login_required
def update_highlight():
    payload = HighlightUpdate(**get_payload(request))
    service = HighlightsService()
    updated_highlight = service.update_highlight(g.user.id, payload)
    return {"status": "ok", "response": asdict(updated_highlight)}


@bp.route("/highlights/set_assignee", methods=["POST"])
@api_login_required
def set_assignee():
    payload = HighlightSetAssignee(**get_payload(request))
    service = HighlightsService()
    updated_action_item = service.set_assignee(payload)
    if payload.assignee_id:
        service.send_action_notification(sender_id=g.user.id, username=g.user.username, view_id=payload.view_id,
                                         assignee_id=payload.assignee_id, action=updated_action_item.content)
    return {"status": "ok", "response": asdict(updated_action_item)}


@bp.route("/highlights/set_completed", methods=["POST"])
@api_login_required
def set_completed():
    payload = HighlightSetCompleted(**get_payload(request))
    service = HighlightsService()
    updated_action_item = service.set_completed(payload)
    return {"status": "ok", "response": asdict(updated_action_item)}


@bp.route("/highlights/comments/create", methods=["POST"])
@api_login_required
def create_comment():
    creator_id = g.user.id
    payload = CommentCreate(**get_payload(request))
    service = HighlightsService()
    comment = service.create_comment(creator_id, payload)
    return {"status": "ok", "response": asdict(comment)}


@bp.route("/highlights/comments/update", methods=["POST"])
@api_login_required
def update_comment():
    user_id = g.user.id
    payload = CommentUpdate(**get_payload(request))
    service = HighlightsService()
    updated_comment = service.update_comment(user_id, payload)
    return {"status": "ok", "response": asdict(updated_comment)}


@bp.route("/highlights/comments/delete", methods=["POST"])
@api_login_required
def delete_comment():
    user_id = g.user.id
    payload = CommentDelete(**get_payload(request))
    service = HighlightsService()
    service.delete_comment(user_id, payload)
    return {"status": "ok"}


@bp.route("/highlights/comments", methods=["GET"])
@api_login_required
def get_comments():
    view_id = UUID(request.args.get("view_id"))
    index = int(request.args.get("index"))
    highlight_created_at = float(request.args.get("created_at"))
    service = HighlightsService()
    comments = service.get_comments(view_id, index, highlight_created_at)
    return {"status": "ok", "response": [asdict(c) for c in comments]}
