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
async def create_highlight(payload: HighlightCreate, user: User = Depends(api_current_user)):
    service = HighlightsService()
    highlight = await service.create(user.id, payload)
    return APIResponse({"status": "ok", "response": asdict(highlight)})


@router.post("/highlights/create_group", name="api.view_api.view_widgets.create_highlight_group")
async def create_highlight_group(payload: HighlightGroupCreate, user: User = Depends(api_current_user)):
    service = HighlightsService()
    action_items = await service.create_group(user.id, payload)
    return APIResponse({"status": "ok", "response": [asdict(action) for action in action_items]})


@router.get("/highlights", name="api.view_api.view_widgets.get_highlights")
async def get_highlights(view_id: UUID = Query(...), index: int = Query(...),
                   user: User = Depends(api_current_user)):
    service = HighlightsService()
    highlights, action_items = await service.get_highlights(view_id, index)
    return APIResponse({
        "status": "ok",
        "response": {
            "highlights": [asdict(h) for h in highlights],
            "action_items": [asdict(a) for a in action_items],
        },
    })


@router.post("/highlights/archive", name="api.view_api.view_widgets.archive_highlight")
async def archive_highlight(payload: HighlightArchive, user: User = Depends(api_current_user)):
    service = HighlightsService()
    await service.archive_highlight(payload)
    return APIResponse({"status": "ok"})


@router.post("/highlights/unarchive", name="api.view_api.view_widgets.unarchive_highlight")
async def unarchive_highlight(payload: HighlightArchive, user: User = Depends(api_current_user)):
    service = HighlightsService()
    await service.unarchive_highlight(payload)
    return APIResponse({"status": "ok"})


@router.post("/highlights/update", name="api.view_api.view_widgets.update_highlight")
async def update_highlight(payload: HighlightUpdate, user: User = Depends(api_current_user)):
    service = HighlightsService()
    updated_highlight = await service.update_highlight(user.id, payload)
    return APIResponse({"status": "ok", "response": asdict(updated_highlight)})


@router.post("/highlights/set_assignee", name="api.view_api.view_widgets.set_assignee")
async def set_assignee(payload: HighlightSetAssignee, user: User = Depends(api_current_user)):
    service = HighlightsService()
    updated_action_item = await service.set_assignee(payload)
    if payload.assignee_id:
        await service.send_action_notification(sender_id=user.id, username=user.username, view_id=payload.view_id,
                                               assignee_id=payload.assignee_id, action=updated_action_item.content)
    return APIResponse({"status": "ok", "response": asdict(updated_action_item)})


@router.post("/highlights/set_completed", name="api.view_api.view_widgets.set_completed")
async def set_completed(payload: HighlightSetCompleted, user: User = Depends(api_current_user)):
    service = HighlightsService()
    updated_action_item = await service.set_completed(payload)
    return APIResponse({"status": "ok", "response": asdict(updated_action_item)})


@router.post("/highlights/comments/create", name="api.view_api.view_widgets.create_comment")
async def create_comment(payload: CommentCreate, user: User = Depends(api_current_user)):
    service = HighlightsService()
    comment = await service.create_comment(user.id, payload)
    return APIResponse({"status": "ok", "response": asdict(comment)})


@router.post("/highlights/comments/update", name="api.view_api.view_widgets.update_comment")
async def update_comment(payload: CommentUpdate, user: User = Depends(api_current_user)):
    service = HighlightsService()
    updated_comment = await service.update_comment(user.id, payload)
    return APIResponse({"status": "ok", "response": asdict(updated_comment)})


@router.post("/highlights/comments/delete", name="api.view_api.view_widgets.delete_comment")
async def delete_comment(payload: CommentDelete, user: User = Depends(api_current_user)):
    service = HighlightsService()
    await service.delete_comment(user.id, payload)
    return APIResponse({"status": "ok"})


@router.get("/highlights/comments", name="api.view_api.view_widgets.get_comments")
async def get_comments(view_id: UUID = Query(...), index: int = Query(...),
                 created_at: float = Query(...),
                 user: User = Depends(api_current_user)):
    service = HighlightsService()
    comments = await service.get_comments(view_id, index, created_at)
    return APIResponse({"status": "ok", "response": [asdict(c) for c in comments]})
