from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from argus.backend.models.web import User
from argus.backend.service.user import api_current_user
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
    HighlightGroupCreate,
)
from argus.backend.util.encoders import APIResponse

router = APIRouter(prefix="/widgets")


@router.post("/highlights/create", name="api.view_api.view_widgets.create_highlight")
def create_highlight(payload: HighlightCreate, user: User = Depends(api_current_user)):
    service = HighlightsService()
    highlight = service.create(user.id, payload)
    return APIResponse({"status": "ok", "response": asdict(highlight)})


@router.post("/highlights/create_group", name="api.view_api.view_widgets.create_highlight_group")
def create_highlight_group(payload: HighlightGroupCreate, user: User = Depends(api_current_user)):
    service = HighlightsService()
    action_items = service.create_group(user.id, payload)
    return APIResponse({"status": "ok", "response": [asdict(action) for action in action_items]})


@router.get("/highlights", name="api.view_api.view_widgets.get_highlights")
def get_highlights(view_id: UUID = Query(...), index: int = Query(...),
                   user: User = Depends(api_current_user)):
    service = HighlightsService()
    highlights, action_items = service.get_highlights(view_id, index)
    return APIResponse({
        "status": "ok",
        "response": {
            "highlights": [asdict(h) for h in highlights],
            "action_items": [asdict(a) for a in action_items],
        },
    })


@router.post("/highlights/archive", name="api.view_api.view_widgets.archive_highlight")
def archive_highlight(payload: HighlightArchive, user: User = Depends(api_current_user)):
    service = HighlightsService()
    service.archive_highlight(payload)
    return APIResponse({"status": "ok"})


@router.post("/highlights/unarchive", name="api.view_api.view_widgets.unarchive_highlight")
def unarchive_highlight(payload: HighlightArchive, user: User = Depends(api_current_user)):
    service = HighlightsService()
    service.unarchive_highlight(payload)
    return APIResponse({"status": "ok"})


@router.post("/highlights/update", name="api.view_api.view_widgets.update_highlight")
def update_highlight(payload: HighlightUpdate, user: User = Depends(api_current_user)):
    service = HighlightsService()
    updated_highlight = service.update_highlight(user.id, payload)
    return APIResponse({"status": "ok", "response": asdict(updated_highlight)})


@router.post("/highlights/set_assignee", name="api.view_api.view_widgets.set_assignee")
def set_assignee(payload: HighlightSetAssignee, user: User = Depends(api_current_user)):
    service = HighlightsService()
    updated_action_item = service.set_assignee(payload)
    if payload.assignee_id:
        service.send_action_notification(sender_id=user.id, username=user.username, view_id=payload.view_id,
                                         assignee_id=payload.assignee_id, action=updated_action_item.content)
    return APIResponse({"status": "ok", "response": asdict(updated_action_item)})


@router.post("/highlights/set_completed", name="api.view_api.view_widgets.set_completed")
def set_completed(payload: HighlightSetCompleted, user: User = Depends(api_current_user)):
    service = HighlightsService()
    updated_action_item = service.set_completed(payload)
    return APIResponse({"status": "ok", "response": asdict(updated_action_item)})


@router.post("/highlights/comments/create", name="api.view_api.view_widgets.create_comment")
def create_comment(payload: CommentCreate, user: User = Depends(api_current_user)):
    service = HighlightsService()
    comment = service.create_comment(user.id, payload)
    return APIResponse({"status": "ok", "response": asdict(comment)})


@router.post("/highlights/comments/update", name="api.view_api.view_widgets.update_comment")
def update_comment(payload: CommentUpdate, user: User = Depends(api_current_user)):
    service = HighlightsService()
    updated_comment = service.update_comment(user.id, payload)
    return APIResponse({"status": "ok", "response": asdict(updated_comment)})


@router.post("/highlights/comments/delete", name="api.view_api.view_widgets.delete_comment")
def delete_comment(payload: CommentDelete, user: User = Depends(api_current_user)):
    service = HighlightsService()
    service.delete_comment(user.id, payload)
    return APIResponse({"status": "ok"})


@router.get("/highlights/comments", name="api.view_api.view_widgets.get_comments")
def get_comments(view_id: UUID = Query(...), index: int = Query(...),
                 created_at: float = Query(...),
                 user: User = Depends(api_current_user)):
    service = HighlightsService()
    comments = service.get_comments(view_id, index, created_at)
    return APIResponse({"status": "ok", "response": [asdict(c) for c in comments]})
