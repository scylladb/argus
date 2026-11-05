from datetime import UTC, datetime
from uuid import UUID

from argus.backend.error_handlers import APIException
from argus.backend.models.chat import ChatMemory, ChatMemoryRevision
from argus.backend.models.web import ArgusRelease, User
from argus.backend.service.chat.entity import ChatEntity
from argus.backend.service.chat.history import touch_state
from argus.backend.util.common import gather_limited

MEMORY_KINDS = ("note", "finding")
MAX_MEMORY_LENGTH = 4000


class ChatMemoryError(APIException):
    pass


def memory_json(memory: ChatMemory, entity_name: str) -> dict:
    return {
        "id": memory.id,
        "entity_id": memory.entity_id,
        "entity_type": memory.entity_type,
        "entity_name": entity_name,
        "kind": memory.kind,
        "content": memory.content,
        "revision": memory.revision,
        "created_by": memory.created_by,
        "created_at": memory.created_at,
        "updated_by": memory.updated_by,
        "updated_at": memory.updated_at,
        "source_node": memory.source_node,
    }


def revision_json(revision: ChatMemoryRevision) -> dict:
    return {
        "revision": revision.revision,
        "memory_id": revision.memory_id,
        "entity_id": revision.entity_id,
        "action": revision.action,
        "before": revision.before,
        "after": revision.after,
        "kind": revision.kind,
        "before_kind": revision.before_kind,
        "user_id": revision.user_id,
        "source": revision.source,
        "source_node": revision.source_node,
        "reverts": revision.reverts,
        "created_at": revision.created_at,
    }


def _clean(content: str | None) -> str:
    content = (content or "").strip()
    if not content:
        raise ChatMemoryError("A memory needs some text")
    if len(content) > MAX_MEMORY_LENGTH:
        raise ChatMemoryError(f"A memory holds at most {MAX_MEMORY_LENGTH} characters")
    return content


def _kind(kind: str) -> str:
    if kind not in MEMORY_KINDS:
        raise ChatMemoryError(f"A memory is a note or a finding, not {kind}")
    return kind


class ChatMemoryService:
    @staticmethod
    async def scope_names(entity: ChatEntity) -> dict[UUID, tuple[str, str]]:
        """Every partition the entity reaches: its own, and for a view, its releases."""
        names = {entity.id: (entity.type, entity.name)}
        if entity.type == "view":
            releases = await gather_limited(ArgusRelease.find_one(id=release_id) for release_id in entity.release_ids)
            names.update({release.id: ("release", release.name) for release in releases if release})
        return names

    async def _locate(self, entity: ChatEntity, memory_id: UUID) -> tuple[ChatMemory, str]:
        for owner, (_, name) in (await self.scope_names(entity)).items():
            memory = await ChatMemory.find_one(entity_id=owner, id=memory_id)
            if memory is not None:
                return memory, name
        raise ChatMemoryError(f"No memory {memory_id} in the scope of {entity.name}")

    async def list(self, entity: ChatEntity) -> list[dict]:
        names = await self.scope_names(entity)
        partitions = await gather_limited(ChatMemory.find(entity_id=owner).all() for owner in names)
        return [memory_json(memory, names[memory.entity_id][1])
                for partition in partitions for memory in partition if not memory.deleted]

    async def _record(self, memory: ChatMemory, action: str, before: str | None, before_kind: str | None,
                      user: User, source_node: UUID | None, reverts: UUID | None = None) -> None:
        revision = ChatMemoryRevision(
            entity_id=memory.entity_id, memory_id=memory.id, action=action, before=before,
            after=None if memory.deleted else memory.content, kind=memory.kind, before_kind=before_kind,
            user_id=user.id, source="chat" if source_node else "manual", source_node=source_node, reverts=reverts,
        )
        await revision.save()
        await memory.update(revision=revision.revision)
        await touch_state(memory.entity_id, memory.entity_type, memory=True)

    async def create(self, entity: ChatEntity, content: str, kind: str, user: User, scope: UUID | None = None,
                     source_node: UUID | None = None) -> dict:
        names = await self.scope_names(entity)
        owner = scope or entity.id
        if owner not in names:
            raise ChatMemoryError(f"{entity.name} cannot write memories for {owner}")
        owner_type, owner_name = names[owner]
        memory = ChatMemory(entity_id=owner, entity_type=owner_type, kind=_kind(kind), content=_clean(content),
                            created_by=user.id, updated_by=user.id, source_node=source_node)
        await memory.save()
        await self._record(memory, "create", None, None, user, source_node)
        return memory_json(memory, owner_name)

    async def update(self, entity: ChatEntity, memory_id: UUID, user: User, *, content: str | None = None,
                     kind: str | None = None, source_node: UUID | None = None) -> dict:
        memory, name = await self._locate(entity, memory_id)
        if memory.deleted:
            raise ChatMemoryError("This memory was deleted; revert its deletion first")
        before, before_kind = memory.content, memory.kind
        fields = {"updated_by": user.id, "updated_at": datetime.now(UTC)}
        if content is not None:
            fields["content"] = _clean(content)
        if kind is not None:
            fields["kind"] = _kind(kind)
        if source_node:
            fields["source_node"] = source_node
        await memory.update(**fields)
        await self._record(memory, "update", before, before_kind, user, source_node)
        return memory_json(memory, name)

    async def delete(self, entity: ChatEntity, memory_id: UUID, user: User, source_node: UUID | None = None) -> dict:
        memory, name = await self._locate(entity, memory_id)
        if memory.deleted:
            raise ChatMemoryError("This memory is already deleted")
        before, before_kind = memory.content, memory.kind
        await memory.update(deleted=True, updated_by=user.id, updated_at=datetime.now(UTC))
        await self._record(memory, "delete", before, before_kind, user, source_node)
        return memory_json(memory, name)

    async def history(self, entity: ChatEntity) -> list[dict]:
        names = await self.scope_names(entity)
        partitions = await gather_limited(ChatMemoryRevision.find(entity_id=owner).all() for owner in names)
        revisions = [revision for partition in partitions for revision in partition]
        revisions.sort(key=lambda revision: revision.revision.time, reverse=True)
        return [revision_json(revision) for revision in revisions]

    async def revert(self, entity: ChatEntity, revision_id: UUID, user: User) -> dict:
        names = await self.scope_names(entity)
        target = None
        for owner in names:
            target = await ChatMemoryRevision.find_one(entity_id=owner, revision=revision_id)
            if target is not None:
                break
        if target is None:
            raise ChatMemoryError(f"No revision {revision_id} in the scope of {entity.name}")
        memory = await ChatMemory.get(entity_id=target.entity_id, id=target.memory_id)
        before = None if memory.deleted else memory.content
        before_kind = memory.kind
        fields = {"updated_by": user.id, "updated_at": datetime.now(UTC)}
        if target.before is None:
            fields["deleted"] = True
        else:
            fields.update(deleted=False, content=target.before, kind=target.before_kind or memory.kind)
        await memory.update(**fields)
        await self._record(memory, "revert", before, before_kind, user, None, reverts=target.revision)
        return memory_json(memory, names[memory.entity_id][1])

    async def scopes(self, entity: ChatEntity) -> list[dict]:
        return [{"id": entity_id, "type": entity_type, "name": name}
                for entity_id, (entity_type, name) in (await self.scope_names(entity)).items()]

    @staticmethod
    async def findings(entity_id: UUID) -> list[dict]:
        memories = await ChatMemory.find(entity_id=entity_id).all()
        return [memory_json(memory, "") for memory in memories if memory.kind == "finding" and not memory.deleted]
