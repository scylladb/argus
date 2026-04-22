import uuid
import pytest
from flask import g

from argus.backend.models.web import (
    ArgusNotification,
    ArgusNotificationState,
    ArgusNotificationSourceTypes,
    ArgusNotificationTypes,
)


def _clear_notifications(receiver_id):
    for n in ArgusNotification.filter(receiver=receiver_id).all():
        n.delete()


def _make_notification(receiver_id, sender_id=None, title="hello", content="world",
                       state=ArgusNotificationState.UNREAD,
                       notification_type=ArgusNotificationTypes.Mention,
                       source_type=ArgusNotificationSourceTypes.Comment,
                       source_id=None) -> ArgusNotification:
    return ArgusNotification(
        receiver=receiver_id,
        sender=sender_id or uuid.uuid4(),
        type=notification_type.value,
        state=state,
        source_type=source_type.value,
        source_id=source_id or uuid.uuid4(),
        title=title,
        content=content,
    ).save()


@pytest.fixture
def cleanup_notifications():
    _clear_notifications(g.user.id)
    yield
    _clear_notifications(g.user.id)


def test_get_unread_count_zero(flask_client, cleanup_notifications):
    res = flask_client.get("/api/v1/notifications/get_unread").json
    assert res["status"] == "ok"
    assert res["response"] == 0


def test_get_unread_count_counts_unread(flask_client, cleanup_notifications):
    for _ in range(3):
        _make_notification(g.user.id)
    res = flask_client.get("/api/v1/notifications/get_unread").json
    assert res["status"] == "ok"
    assert res["response"] == 3


def test_get_unread_count_excludes_read(flask_client, cleanup_notifications):
    _make_notification(g.user.id, state=ArgusNotificationState.UNREAD)
    _make_notification(g.user.id, state=ArgusNotificationState.READ)
    _make_notification(g.user.id, state=ArgusNotificationState.READ)
    res = flask_client.get("/api/v1/notifications/get_unread").json
    assert res["response"] == 1


def test_get_summary_returns_short_summaries(flask_client, cleanup_notifications):
    created = [_make_notification(g.user.id, title=f"title-{i}") for i in range(3)]
    res = flask_client.get("/api/v1/notifications/summary").json
    assert res["status"] == "ok"
    assert len(res["response"]) == 3
    titles = {item["title"] for item in res["response"]}
    assert titles == {n.title for n in created}
    # short summary fields only
    sample = res["response"][0]
    assert set(sample.keys()) == {"receiver", "sender", "id", "created", "title", "state"}


def test_get_summary_respects_limit(flask_client, cleanup_notifications):
    for i in range(5):
        _make_notification(g.user.id, title=f"t-{i}")
    res = flask_client.get("/api/v1/notifications/summary?limit=2").json
    assert len(res["response"]) == 2


def test_get_summary_default_limit(flask_client, cleanup_notifications):
    for i in range(25):
        _make_notification(g.user.id, title=f"t-{i}")
    res = flask_client.get("/api/v1/notifications/summary").json
    assert len(res["response"]) == 20


def test_get_summary_after_id_paginates(flask_client, cleanup_notifications):
    for i in range(5):
        _make_notification(g.user.id, title=f"t-{i}")
    full = flask_client.get("/api/v1/notifications/summary").json["response"]
    assert len(full) == 5
    # Clustering DESC, id__lte filters to newer-or-equal? id__lte means id <= after.
    # Picking the third newest notification id and asking for after=that should return items <= it (older or same).
    pivot = full[2]["id"]
    page = flask_client.get(f"/api/v1/notifications/summary?afterId={pivot}").json["response"]
    assert len(page) == 3
    assert page[0]["id"] == pivot


def test_get_notification_returns_full_dict(flask_client, cleanup_notifications):
    n = _make_notification(g.user.id, title="full", content="body")
    res = flask_client.get(f"/api/v1/notifications/get?id={n.id}").json
    assert res["status"] == "ok"
    body = res["response"]
    assert body["title"] == "full"
    assert body["content"] == "body"
    assert body["type"] == ArgusNotificationTypes.Mention.value
    assert body["source"] == ArgusNotificationSourceTypes.Comment.value
    assert body["state"] == ArgusNotificationState.UNREAD


def test_get_notification_missing_id_errors(flask_client, cleanup_notifications):
    res = flask_client.get("/api/v1/notifications/get").json
    assert res["status"] == "error"
    assert "No notification id provided" in res["response"]["arguments"][0]


def test_get_notification_unknown_id_errors(flask_client, cleanup_notifications):
    bogus = uuid.uuid1()
    res = flask_client.get(f"/api/v1/notifications/get?id={bogus}").json
    assert res["status"] == "error"
    assert res["response"]["exception"] == "DoesNotExist"


def test_read_notification_marks_read_and_decrements_unread(flask_client, cleanup_notifications):
    n = _make_notification(g.user.id)
    other = _make_notification(g.user.id)

    pre = flask_client.get("/api/v1/notifications/get_unread").json["response"]
    assert pre == 2

    res = flask_client.post(
        "/api/v1/notifications/read",
        json={"id": str(n.id)},
    ).json
    assert res["status"] == "ok"
    assert res["response"] is True

    post = flask_client.get("/api/v1/notifications/get_unread").json["response"]
    assert post == 1

    # Confirm via get endpoint
    fetched = flask_client.get(f"/api/v1/notifications/get?id={n.id}").json["response"]
    assert fetched["state"] == ArgusNotificationState.READ
    other_fetched = flask_client.get(f"/api/v1/notifications/get?id={other.id}").json["response"]
    assert other_fetched["state"] == ArgusNotificationState.UNREAD


def test_read_notification_unknown_id_errors(flask_client, cleanup_notifications):
    bogus = uuid.uuid1()
    res = flask_client.post(
        "/api/v1/notifications/read",
        json={"id": str(bogus)},
    ).json
    assert res["status"] == "error"
    assert res["response"]["exception"] == "DoesNotExist"
