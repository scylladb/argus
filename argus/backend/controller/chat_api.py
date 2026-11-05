import json
from collections.abc import AsyncIterator
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from starlette.responses import Response, StreamingResponse

from argus.backend.models.web import User, UserRoles
from argus.backend.service.chat.actions import Seed
from argus.backend.service.chat.entity import ChatEntity, resolve_entity
from argus.backend.service.chat.hub import ChatHub, default_hub
from argus.backend.service.chat.identity import ChatIdentityService
from argus.backend.service.chat.memory import ChatMemoryService
from argus.backend.service.chat.service import ChatService
from argus.backend.service.user import api_current_user, require_roles
from argus.backend.util.encoders import APIResponse, ArgusJSONEncoder

router = APIRouter(prefix="/chat/{entity_type}/{entity_id}")
identity_router = APIRouter(prefix="/chat/identity")
RECONNECT_MS = 1000


class MessageRequest(BaseModel):
    content: str
    auto: bool = False


class RegenerateRequest(BaseModel):
    auto: bool = False


class HeadRequest(BaseModel):
    node: UUID


class StartParamsRequest(BaseModel):
    tests: dict[str, dict[str, str]]
    seed: Literal["last_build", "defaults", "build"] | None = None
    build_number: int | None = None


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    kind: str = "note"
    scope: UUID | None = None


class MemoryUpdateRequest(BaseModel):
    content: str | None = None
    kind: str | None = None


@identity_router.get("/{connection}/picture", name="api.chat_api.identity_picture")
async def identity_picture(connection: str, user: User = Depends(api_current_user)):
    picture = await ChatIdentityService().picture(connection)
    if picture is None:
        return Response("Not found", status_code=404, media_type="text/plain")
    content, media_type = picture
    return Response(content, media_type=media_type,
                    headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


async def chat_entity(entity_type: str, entity_id: UUID) -> ChatEntity:
    return await resolve_entity(entity_type, entity_id)


def ok(response) -> APIResponse:
    return APIResponse({"status": "ok", "response": response})


@router.get("/memories", name="api.chat_api.list_memories")
async def list_memories(entity: ChatEntity = Depends(chat_entity), user: User = Depends(api_current_user)):
    return ok(await ChatMemoryService().list(entity))


@router.post("/memories", name="api.chat_api.create_memory")
async def create_memory(payload: MemoryCreateRequest, entity: ChatEntity = Depends(chat_entity),
                        user: User = Depends(api_current_user)):
    return ok(await ChatMemoryService().create(entity, payload.content, payload.kind, user, scope=payload.scope))


@router.get("/memories/history", name="api.chat_api.memory_history")
async def memory_history(entity: ChatEntity = Depends(chat_entity), user: User = Depends(api_current_user)):
    return ok(await ChatMemoryService().history(entity))


@router.post("/memories/history/{revision}/revert", name="api.chat_api.revert_memory")
async def revert_memory(revision: UUID, entity: ChatEntity = Depends(chat_entity),
                        user: User = Depends(api_current_user)):
    return ok(await ChatMemoryService().revert(entity, revision, user))


@router.put("/memories/{memory_id}", name="api.chat_api.update_memory")
async def update_memory(memory_id: UUID, payload: MemoryUpdateRequest, entity: ChatEntity = Depends(chat_entity),
                        user: User = Depends(api_current_user)):
    return ok(await ChatMemoryService().update(entity, memory_id, user, content=payload.content, kind=payload.kind))


@router.delete("/memories/{memory_id}", name="api.chat_api.delete_memory")
async def delete_memory(memory_id: UUID, entity: ChatEntity = Depends(chat_entity),
                        user: User = Depends(api_current_user)):
    return ok(await ChatMemoryService().delete(entity, memory_id, user))


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, cls=ArgusJSONEncoder)}\n\n"


async def event_stream(entity: ChatEntity, user: User, service: ChatService, hub: ChatHub) -> AsyncIterator[str]:
    subscription = hub.open(entity, user)
    try:
        yield f"retry: {RECONNECT_MS}\n\n"
        yield sse({"type": "snapshot", "conversation": await service.conversation(entity)})
        async for event in subscription.events():
            yield sse(event)
    finally:
        subscription.close()


@router.get("", name="api.chat_api.conversation")
async def conversation(entity: ChatEntity = Depends(chat_entity), user: User = Depends(api_current_user)):
    return ok(await ChatService().conversation(entity))


@router.delete("", name="api.chat_api.wipe")
async def wipe(entity: ChatEntity = Depends(chat_entity), user: User = Depends(require_roles(UserRoles.Admin))):
    return ok(await ChatService().wipe(entity))


@router.get("/meta", name="api.chat_api.meta")
async def meta(entity: ChatEntity = Depends(chat_entity), user: User = Depends(api_current_user)):
    return ok(await ChatService().meta(entity))


@router.get("/events", name="api.chat_api.events")
async def events(entity: ChatEntity = Depends(chat_entity), user: User = Depends(api_current_user)):
    return StreamingResponse(event_stream(entity, user, ChatService(), default_hub), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/messages", name="api.chat_api.send")
async def send(payload: MessageRequest, entity: ChatEntity = Depends(chat_entity),
               user: User = Depends(api_current_user)):
    return ok(await ChatService().send(entity, payload.content, user, payload.auto))


@router.post("/regenerate", name="api.chat_api.regenerate")
async def regenerate(payload: RegenerateRequest | None = None, entity: ChatEntity = Depends(chat_entity),
                     user: User = Depends(api_current_user)):
    return ok(await ChatService().regenerate(entity, user, bool(payload and payload.auto)))


@router.post("/compact", name="api.chat_api.compact")
async def compact(entity: ChatEntity = Depends(chat_entity), user: User = Depends(api_current_user)):
    return ok(await ChatService().compact(entity, user))


@router.post("/undo", name="api.chat_api.undo")
async def undo(entity: ChatEntity = Depends(chat_entity), user: User = Depends(api_current_user)):
    return ok(await ChatService().undo(entity))


@router.post("/head", name="api.chat_api.set_head")
async def set_head(payload: HeadRequest, entity: ChatEntity = Depends(chat_entity),
                   user: User = Depends(api_current_user)):
    return ok(await ChatService().set_head(entity, payload.node))


@router.post("/stop", name="api.chat_api.stop")
async def stop(entity: ChatEntity = Depends(chat_entity), user: User = Depends(api_current_user)):
    return ok({"stopping": await ChatService().stop(entity)})


@router.post("/actions/{node}/confirm", name="api.chat_api.confirm_action")
async def confirm_action(node: UUID, entity: ChatEntity = Depends(chat_entity),
                         user: User = Depends(api_current_user)):
    return ok(await ChatService().confirm(entity, node, user))


@router.post("/actions/{node}/dismiss", name="api.chat_api.dismiss_action")
async def dismiss_action(node: UUID, entity: ChatEntity = Depends(chat_entity),
                         user: User = Depends(api_current_user)):
    return ok(await ChatService().dismiss(entity, node, user))


@router.post("/actions/{node}/refresh", name="api.chat_api.refresh_action")
async def refresh_action(node: UUID, entity: ChatEntity = Depends(chat_entity),
                         user: User = Depends(api_current_user)):
    return ok(await ChatService().refresh(entity, node))


@router.post("/actions/{node}/params", name="api.chat_api.adjust_action")
async def adjust_action(node: UUID, payload: StartParamsRequest, entity: ChatEntity = Depends(chat_entity),
                        user: User = Depends(api_current_user)):
    seed = Seed.of(payload.seed, payload.build_number) if payload.seed or payload.build_number else None
    return ok(await ChatService().adjust(entity, node, payload.tests, seed))
