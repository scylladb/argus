from uuid import uuid1

import pytest

from argus.backend.service.chat.entity import resolve_entity
from argus.backend.service.chat.history import ChatHistoryService
from argus.backend.service.chat.memory import ChatMemoryError, ChatMemoryService
from argus.backend.tests.chat.helpers import seed_entity_release, seed_view

pytestmark = pytest.mark.docker_required


@pytest.fixture
async def release_entity(release_manager_service):
    seeded = await seed_entity_release(release_manager_service)
    return await resolve_entity("release", seeded.release.id)


async def test_a_memory_is_created_edited_and_deleted_with_its_history(release_entity, logged_in_user):
    service = ChatMemoryService()

    created = await service.create(release_entity, "We run tests on GCE", "note", logged_in_user)
    edited = await service.update(release_entity, created["id"], logged_in_user, content="We run tests on AWS",
                                  kind="finding")
    deleted = await service.delete(release_entity, created["id"], logged_in_user)

    assert (created["kind"], created["entity_name"], created["created_by"]) == (
        "note", release_entity.name, logged_in_user.id)
    assert (edited["content"], edited["kind"]) == ("We run tests on AWS", "finding")
    assert deleted["id"] == created["id"]
    assert await service.list(release_entity) == []
    history = await service.history(release_entity)
    assert [(entry["action"], entry["before"], entry["after"]) for entry in history] == [
        ("delete", "We run tests on AWS", None),
        ("update", "We run tests on GCE", "We run tests on AWS"),
        ("create", None, "We run tests on GCE"),
    ]
    assert all(entry["user_id"] == logged_in_user.id and entry["source"] == "manual" for entry in history)


async def test_reverting_restores_the_state_before_a_revision(release_entity, logged_in_user):
    service = ChatMemoryService()
    created = await service.create(release_entity, "GCE", "note", logged_in_user)
    await service.update(release_entity, created["id"], logged_in_user, content="AWS", kind="finding")
    await service.delete(release_entity, created["id"], logged_in_user)
    delete_revision, update_revision, create_revision = await service.history(release_entity)

    restored = await service.revert(release_entity, delete_revision["revision"], logged_in_user)
    assert (restored["content"], restored["kind"]) == ("AWS", "finding")

    before_update = await service.revert(release_entity, update_revision["revision"], logged_in_user)
    assert (before_update["content"], before_update["kind"]) == ("GCE", "note")

    await service.revert(release_entity, create_revision["revision"], logged_in_user)
    assert await service.list(release_entity) == []

    latest = (await service.history(release_entity))[0]
    assert (latest["action"], latest["reverts"]) == ("revert", create_revision["revision"])


async def test_a_view_sees_its_releases_memories_but_writes_only_in_scope(release_manager_service,
                                                                          logged_in_user):
    inside = await seed_entity_release(release_manager_service)
    outside = await seed_entity_release(release_manager_service)
    view = await resolve_entity("view", (await seed_view(logged_in_user, inside.tests)).id)
    release = await resolve_entity("release", inside.release.id)
    service = ChatMemoryService()

    await service.create(release, "Release convention", "note", logged_in_user)
    await service.create(view, "View convention", "note", logged_in_user)
    in_release = await service.create(view, "Written from the view", "note", logged_in_user,
                                      scope=inside.release.id)

    seen = {(memory["content"], memory["entity_type"]) for memory in await service.list(view)}
    assert seen == {("Release convention", "release"), ("View convention", "view"),
                    ("Written from the view", "release")}
    assert in_release["entity_id"] == inside.release.id
    assert {memory["content"] for memory in await service.list(release)} == {
        "Release convention", "Written from the view"}
    with pytest.raises(ChatMemoryError):
        await service.create(view, "Elsewhere", "note", logged_in_user, scope=outside.release.id)


async def test_a_release_cannot_touch_a_views_memory(release_manager_service, logged_in_user):
    seeded = await seed_entity_release(release_manager_service)
    view = await resolve_entity("view", (await seed_view(logged_in_user, seeded.tests)).id)
    release = await resolve_entity("release", seeded.release.id)
    service = ChatMemoryService()
    memory = await service.create(view, "View only", "note", logged_in_user)

    with pytest.raises(ChatMemoryError):
        await service.update(release, memory["id"], logged_in_user, content="hijacked")


async def test_a_memory_needs_content_and_a_known_kind(release_entity, logged_in_user):
    service = ChatMemoryService()

    with pytest.raises(ChatMemoryError):
        await service.create(release_entity, "  ", "note", logged_in_user)
    with pytest.raises(ChatMemoryError):
        await service.create(release_entity, "text", "rumour", logged_in_user)


async def test_a_change_from_the_chat_records_its_source_and_touches_the_state(release_entity, logged_in_user):
    service = ChatMemoryService()
    node = uuid1()

    memory = await service.create(release_entity, "Finding", "finding", logged_in_user, source_node=node)

    state = await ChatHistoryService(release_entity).state()
    revision = (await service.history(release_entity))[0]
    assert memory["source_node"] == node
    assert (revision["source"], revision["source_node"]) == ("chat", node)
    assert state.memory_changed_at is not None


async def test_findings_are_the_finding_memories(release_entity, logged_in_user):
    service = ChatMemoryService()
    await service.create(release_entity, "A note", "note", logged_in_user)
    finding = await service.create(release_entity, "rc3 failures are infra", "finding", logged_in_user)

    assert [memory["id"] for memory in await service.findings(release_entity.id)] == [finding["id"]]
