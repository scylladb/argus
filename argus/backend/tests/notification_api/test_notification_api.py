import uuid
import pytest
from flask import g

from argus.backend.models.web import (
    ArgusNotification,
    ArgusNotificationState,
    ArgusNotificationSourceTypes,
    ArgusNotificationTypes,
)


@pytest.fixture
def make_notification():
    """Factory creating notifications; deletes only the rows it created in teardown."""
    created = []

    def _make(receiver_id, sender_id=None, title="hello", content="world",
              state=ArgusNotificationState.UNREAD,
              notification_type=ArgusNotificationTypes.Mention,
              source_type=ArgusNotificationSourceTypes.Comment,
              source_id=None) -> ArgusNotification:
        notification = ArgusNotification(
            receiver=receiver_id,
            sender=sender_id or uuid.uuid4(),
            type=notification_type.value,
            state=state,
            source_type=source_type.value,
            source_id=source_id or uuid.uuid4(),
            title=title,
            content=content,
        )
        notification.save()
        created.append(notification)
        return notification

    yield _make

    for notification in created:
        try:
            notification.delete()
        except Exception:
            pass


def test_get_unread_count_zero(api_client):
    res = api_client.get("/api/v1/notifications/get_unread").json()
    assert res["status"] == "ok"
    assert res["response"] == 0


def test_get_unread_count_counts_unread(api_client, make_notification):
    for _ in range(3):
        make_notification(g.user.id)


def test_get_unread_count_excludes_read(api_client, make_notification):
    make_notification(g.user.id, state=ArgusNotificationState.UNREAD)
    make_notification(g.user.id, state=ArgusNotificationState.READ)
    make_notification(g.user.id, state=ArgusNotificationState.READ)
    res = api_client.get("/api/v1/notifications/get_unread").json()
    assert res["response"] == 1


def test_get_summary_returns_short_summaries(api_client, make_notification):
    created = [make_notification(g.user.id, title=f"title-{i}") for i in range(3)]
    res = api_client.get("/api/v1/notifications/summary").json()
    assert res["status"] == "ok"
    assert len(res["response"]) == 3
    titles = {item["title"] for item in res["response"]}
    assert titles == {n.title for n in created}
    # short summary fields only
    sample = res["response"][0]
    assert set(sample.keys()) == {"receiver", "sender", "id", "created", "title", "state"}


def test_get_summary_respects_limit(api_client, make_notification):
    for i in range(5):
        make_notification(g.user.id, title=f"t-{i}")
    res = api_client.get("/api/v1/notifications/summary?limit=2").json()
    assert len(res["response"]) == 2


def test_get_summary_default_limit(api_client, make_notification):
    for i in range(25):
        make_notification(g.user.id, title=f"t-{i}")
    res = api_client.get("/api/v1/notifications/summary").json()
    assert len(res["response"]) == 20


def test_get_summary_after_id_paginates(api_client, make_notification):
    for i in range(5):
        make_notification(g.user.id, title=f"t-{i}")
    full = api_client.get("/api/v1/notifications/summary").json()["response"]
    assert len(full) == 5
    # Clustering DESC, id__lte filters to newer-or-equal? id__lte means id <= after.
    # Picking the third newest notification id and asking for after=that should return items <= it (older or same).
    pivot = full[2]["id"]
    page = api_client.get(f"/api/v1/notifications/summary?afterId={pivot}").json()["response"]
    assert len(page) == 3
    assert page[0]["id"] == pivot


def test_get_notification_returns_full_dict(api_client, make_notification):
    n = make_notification(g.user.id, title="full", content="body")
    res = api_client.get(f"/api/v1/notifications/get?id={n.id}").json()
    assert res["status"] == "ok"
    body = res["response"]
    assert body["title"] == "full"
    assert body["content"] == "body"
    assert body["type"] == ArgusNotificationTypes.Mention.value
    assert body["source"] == ArgusNotificationSourceTypes.Comment.value
    assert body["state"] == ArgusNotificationState.UNREAD


def test_get_notification_missing_id_errors(api_client):
    res = api_client.get("/api/v1/notifications/get").json()
    assert res["status"] == "error"
    assert res["response"]["exception"] == "RequestValidationError"


def test_get_notification_unknown_id_errors(api_client):
    bogus = uuid.uuid1()
    res = api_client.get(f"/api/v1/notifications/get?id={bogus}").json()
    assert res["status"] == "error"
    assert res["response"]["exception"] == "DocumentNotFound"


def test_read_notification_marks_read_and_decrements_unread(api_client, make_notification):
    n = make_notification(g.user.id)
    other = make_notification(g.user.id)

    pre = api_client.get("/api/v1/notifications/get_unread").json()["response"]
    assert pre == 2

    res = api_client.post(
        "/api/v1/notifications/read",
        json={"id": str(n.id)},
    ).json()
    assert res["status"] == "ok"
    assert res["response"] is True

    post = api_client.get("/api/v1/notifications/get_unread").json()["response"]
    assert post == 1

    # Confirm via get endpoint
    fetched = api_client.get(f"/api/v1/notifications/get?id={n.id}").json()["response"]
    assert fetched["state"] == ArgusNotificationState.READ
    other_fetched = api_client.get(f"/api/v1/notifications/get?id={other.id}").json()["response"]
    assert other_fetched["state"] == ArgusNotificationState.UNREAD


def test_read_notification_unknown_id_errors(api_client):
    bogus = uuid.uuid1()
    res = api_client.post(
        "/api/v1/notifications/read",
        json={"id": str(bogus)},
    ).json()
    assert res["status"] == "error"
    assert res["response"]["exception"] == "DocumentNotFound"
