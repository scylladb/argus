import uuid
from datetime import UTC, datetime, timedelta
from uuid import uuid1

import pytest

from argus.backend.service.chat.entity import ChatEntityError, resolve_entity
from argus.backend.service.chat.history import (
    ChatBusyError,
    ChatHistoryError,
    ChatHistoryService,
    active_path,
)
from argus.backend.service.chat.hub import ChatHub
from argus.backend.service.chat.service import ChatService
from argus.backend.tests.chat.helpers import seed_entity_release, seed_view

pytestmark = pytest.mark.docker_required


async def history_for_new_release(release_manager_service) -> ChatHistoryService:
    seeded = await seed_entity_release(release_manager_service)
    return ChatHistoryService(await resolve_entity("release", seeded.release.id))


async def exchange(history: ChatHistoryService, user, question: str, answer: str, parent=None):
    """A user node and its assistant answer under ``parent``, with head moved to the answer."""
    state, _ = await history.read()
    asked = await history.append(role="user", content=question, user_id=user.id, parent=parent or state.head)
    answered = await history.append(role="assistant", content=answer, user_id=user.id, parent=asked.node)
    assert await history.move_head(state.head, answered.node)
    return asked, answered


async def test_a_release_entity_reaches_all_of_its_tests(release_manager_service):
    seeded = await seed_entity_release(release_manager_service)

    entity = await resolve_entity("release", seeded.release.id)

    assert (entity.type, entity.name, entity.release_ids, entity.test_ids) == (
        "release", seeded.release.name, (seeded.release.id,), None)


async def test_a_view_entity_reaches_its_tests_and_their_releases(release_manager_service, logged_in_user):
    first = await seed_entity_release(release_manager_service)
    second = await seed_entity_release(release_manager_service)
    view = await seed_view(logged_in_user, [first.tests[0], second.tests[1]])

    entity = await resolve_entity("view", view.id)

    assert entity.type == "view"
    assert entity.name == view.display_name
    assert set(entity.release_ids) == {first.release.id, second.release.id}
    assert entity.test_ids == frozenset({first.tests[0].id, second.tests[1].id})


async def test_an_unknown_entity_is_refused():
    with pytest.raises(ChatEntityError):
        await resolve_entity("release", uuid.uuid4())
    with pytest.raises(ChatEntityError):
        await resolve_entity("plan", uuid.uuid4())


async def test_the_active_path_follows_head(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    first_q, first_a = await exchange(history, logged_in_user, "what failed?", "two tests")
    second_q, second_a = await exchange(history, logged_in_user, "which ones?", "a and b")

    state, nodes = await history.read()

    assert state.head == second_a.node
    assert [node.content for node in active_path(nodes, state.head)] == [
        "what failed?", "two tests", "which ones?", "a and b"]


async def test_try_again_adds_a_sibling_and_set_head_switches_back(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    asked, first = await exchange(history, logged_in_user, "what failed?", "first try")
    second = await history.append(role="assistant", content="second try", parent=asked.node)
    assert await history.move_head(first.node, second.node)

    _, nodes = await history.read()
    assert [node.content for node in active_path(nodes, second.node)][-1] == "second try"

    head = await history.set_head(first.node)

    state, nodes = await history.read()
    assert head == first.node == state.head
    assert [node.content for node in active_path(nodes, state.head)] == ["what failed?", "first try"]


async def test_set_head_goes_to_the_newest_leaf_below_the_node(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    asked, answered = await exchange(history, logged_in_user, "q1", "a1")
    _, deeper = await exchange(history, logged_in_user, "q2", "a2")
    other = await history.append(role="assistant", content="a1 again", parent=asked.node)
    assert await history.move_head(deeper.node, other.node)

    assert await history.set_head(answered.node) == deeper.node


async def test_undo_drops_the_last_exchange_and_hides_it(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    _, first_a = await exchange(history, logged_in_user, "q1", "a1")
    second_q, second_a = await exchange(history, logged_in_user, "q2", "a2")
    tool = await history.append(role="tool", content="{}", parent=second_a.node)
    assert await history.move_head(second_a.node, tool.node)

    head = await history.undo()

    state, nodes = await history.read()
    by_id = {node.node: node for node in nodes}
    assert head == first_a.node == state.head
    assert all(by_id[node].hidden for node in (second_q.node, second_a.node, tool.node))
    assert not by_id[first_a.node].hidden


async def test_undo_removes_a_compaction_summary_alone(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    _, answered = await exchange(history, logged_in_user, "q1", "a1")
    summary = await history.append(role="summary", content="short", parent=answered.node)
    assert await history.move_head(answered.node, summary.node)

    assert await history.undo() == answered.node


async def test_undo_with_nothing_to_undo_is_refused(release_manager_service):
    history = await history_for_new_release(release_manager_service)

    with pytest.raises(ChatHistoryError):
        await history.undo()


async def test_move_head_with_a_stale_expected_head_is_not_applied(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    _, answered = await exchange(history, logged_in_user, "q1", "a1")

    assert await history.move_head(None, uuid1()) is False
    state, _ = await history.read()
    assert state.head == answered.node


async def test_one_generation_at_a_time(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    first, second = uuid1(), uuid1()

    await history.acquire(logged_in_user, first)
    with pytest.raises(ChatBusyError, match="Answering the question of"):
        await history.acquire(logged_in_user, second)
    with pytest.raises(ChatBusyError):
        await history.undo()

    await history.release(first)
    await history.acquire(logged_in_user, second)
    state, _ = await history.read()
    assert (state.busy, state.busy_user) == (second, logged_in_user.id)


async def test_an_abandoned_lock_is_taken_over_and_its_node_marked_failed(release_manager_service,
                                                                          logged_in_user):
    history = await history_for_new_release(release_manager_service)
    abandoned = await history.append(role="assistant", content="half", status="streaming")
    await history.acquire(logged_in_user, abandoned.node,
                          now=datetime.now(UTC) - timedelta(minutes=6))

    taker = uuid1()
    await history.acquire(logged_in_user, taker)

    state, nodes = await history.read()
    assert state.busy == taker
    assert next(node for node in nodes if node.node == abandoned.node).status == "error"


async def test_releasing_someone_elses_lock_does_nothing(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    holder = uuid1()
    await history.acquire(logged_in_user, holder)

    await history.release(uuid1())

    state, _ = await history.read()
    assert state.busy == holder


async def test_every_write_touches_the_state(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    before, _ = await history.read()

    node = await history.append(role="user", content="q", user_id=logged_in_user.id)
    after_append, _ = await history.read()
    await history.flush(node, content="q2")
    after_flush, nodes = await history.read()

    assert before.changed_at is None
    assert after_append.changed_at is not None
    assert after_flush.changed_at >= after_append.changed_at
    assert nodes[0].content == "q2"


async def test_wipe_removes_the_conversation_and_keeps_the_chat_usable(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    await exchange(history, logged_in_user, "q1", "a1")

    await history.wipe()

    state, nodes = await history.read()
    assert (nodes, state.head) == ([], None)
    await exchange(history, logged_in_user, "q2", "a2")
    assert len((await history.read())[1]) == 2


async def test_wipe_waits_for_the_running_answer(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    await history.acquire(logged_in_user, uuid1())

    with pytest.raises(ChatBusyError):
        await history.wipe()


async def test_stop_frees_a_lock_nobody_refreshed(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    abandoned = await history.append(role="assistant", content="half", status="streaming")
    await history.acquire(logged_in_user, abandoned.node, now=datetime.now(UTC) - timedelta(minutes=6))

    stopped = await ChatService(ChatHub()).stop(history.entity)

    state, nodes = await history.read()
    assert stopped == abandoned.node and state.busy is None
    assert next(node for node in nodes if node.node == abandoned.node).status == "error"


async def test_a_heartbeat_keeps_only_its_own_lock_fresh(release_manager_service, logged_in_user):
    history = await history_for_new_release(release_manager_service)
    holder = uuid1()
    await history.acquire(logged_in_user, holder, now=datetime.now(UTC) - timedelta(minutes=6))

    await history.heartbeat(uuid1())
    stale = await history.release_stale()
    await history.acquire(logged_in_user, holder, now=datetime.now(UTC) - timedelta(minutes=6))
    await history.heartbeat(holder)
    kept = not await history.release_stale()

    assert stale is True and kept is True


async def test_no_question_starts_while_the_tree_changes(release_manager_service, logged_in_user, chat_model):
    history = await history_for_new_release(release_manager_service)

    async with history.holding():
        with pytest.raises(ChatBusyError):
            await ChatService(ChatHub()).send(history.entity, "q", logged_in_user)
        with pytest.raises(ChatBusyError):
            await history.undo()

    assert (await history.state()).busy is None
