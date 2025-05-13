import json
from datetime import datetime, UTC
from unittest.mock import patch
from uuid import uuid4, UUID

from flask import g

from argus.backend.models.view_widgets import WidgetHighlights, WidgetComment


@patch("argus.backend.service.views_widgets.highlights.HighlightsService._send_highlight_notifications")
def test_create_highlight_should_return_created_highlight(notifications, flask_client):
    view_id = str(uuid4())
    now = datetime.now(UTC)
    response = flask_client.post(
        "/api/v1/views/widgets/highlights/create",
        data=json.dumps({"view_id": view_id, "index": 0, "content": "Highlight content", "is_task": False}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.text
    assert response.json["status"] == "ok"
    assert response.json["response"]["view_id"] == view_id
    assert response.json["response"]["content"] == "Highlight content"
    assert response.json["response"]["archived_at"] == 0
    assert response.json["response"]["comments_count"] == 0
    assert response.json["response"]["creator_id"] == str(g.user.id)
    assert response.json["response"]["created_at"] > now.timestamp()
    assert "completed" not in response.json["response"]
    assert "assignee_id" not in response.json["response"]


@patch("argus.backend.service.views_widgets.highlights.HighlightsService._send_highlight_notifications")
def test_create_action_item_should_return_created_action_item(notifications, flask_client):
    view_id = str(uuid4())
    now = datetime.now(UTC)
    response = flask_client.post(
        "/api/v1/views/widgets/highlights/create",
        data=json.dumps({"view_id": view_id, "index": 0, "content": "Action item content", "is_task": True}),
        content_type="application/json",
    )

    assert response.status_code == 200, response.text
    assert response.json["status"] == "ok"
    assert response.json["response"]["view_id"] == view_id
    assert response.json["response"]["content"] == "Action item content"
    assert response.json["response"]["completed"] is False
    assert response.json["response"]["assignee_id"] is None
    assert response.json["response"]["archived_at"] == 0
    assert response.json["response"]["comments_count"] == 0
    assert response.json["response"]["creator_id"] == str(g.user.id)
    assert response.json["response"]["created_at"] > now.timestamp()


def test_get_highlights_should_return_highlights_and_action_items(flask_client):
    view_id = str(uuid4())
    creator_id = g.user.id

    highlight_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=datetime.now(UTC),
        creator_id=creator_id,
        content="Test highlight",
        completed=None,
        comments_count=0,
    )
    highlight_entry.save()

    action_item_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=datetime.now(UTC),
        creator_id=creator_id,
        content="Test action item",
        completed=False,
        comments_count=0,
    )
    action_item_entry.save()

    response = flask_client.get(f"/api/v1/views/widgets/highlights?view_id={view_id}&index=0")

    assert response.status_code == 200
    assert response.json["status"] == "ok"
    highlights = response.json["response"]["highlights"]
    action_items = response.json["response"]["action_items"]

    assert len(highlights) == 1
    assert len(action_items) == 1
    assert highlights[0]["content"] == "Test highlight"
    assert action_items[0]["content"] == "Test action item"


def test_archive_highlight_should_mark_highlight_as_archived(flask_client):
    view_id = str(uuid4())
    created_at = datetime.now(UTC)
    creator_id = g.user.id
    highlight_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=created_at,
        creator_id=creator_id,
        content="Test highlight",
        completed=None,
        comments_count=0,
        archived_at=datetime.fromtimestamp(0, tz=UTC),
    )
    highlight_entry.save()

    response = flask_client.post(
        "/api/v1/views/widgets/highlights/archive",
        data=json.dumps(
            {
                "view_id": view_id,
                "index": 0,
                "created_at": created_at.timestamp(),
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json["status"] == "ok"

    archived_entry = WidgetHighlights.objects(view_id=UUID(view_id), index=0, created_at=created_at).first()
    assert archived_entry.archived_at.replace(tzinfo=UTC) > created_at


def test_unarchive_highlight_should_unmark_highlight_from_archived(flask_client):
    view_id = str(uuid4())
    created_at = datetime.now(UTC)
    creator_id = g.user.id
    archived_time = datetime.now(UTC)
    highlight_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=created_at,
        creator_id=creator_id,
        content="Test highlight",
        completed=None,
        comments_count=0,
        archived_at=archived_time,
    )
    highlight_entry.save()

    response = flask_client.post(
        "/api/v1/views/widgets/highlights/unarchive",
        data=json.dumps(
            {
                "view_id": view_id,
                "index": 0,
                "created_at": created_at.timestamp(),
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json["status"] == "ok"

    unarchived_entry = WidgetHighlights.objects(view_id=UUID(view_id), index=0, created_at=created_at).first()
    assert unarchived_entry.archived_at.replace(tzinfo=UTC) == datetime.fromtimestamp(0, tz=UTC)


@patch("argus.backend.service.views_widgets.highlights.HighlightsService._send_highlight_notifications")
def test_update_highlight_should_update_content_for_creator(notifications, flask_client):
    view_id = str(uuid4())
    created_at = datetime.now(UTC)
    creator_id = g.user.id
    original_content = "Original content"
    updated_content = "Updated content"

    highlight_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=created_at,
        creator_id=creator_id,
        content=original_content,
        completed=None,
        comments_count=0,
        archived_at=datetime.fromtimestamp(0, tz=UTC),
    )
    highlight_entry.save()

    response = flask_client.post(
        "/api/v1/views/widgets/highlights/update",
        data=json.dumps({
            "view_id": view_id,
            "index": 0,
            "created_at": created_at.timestamp(),
            "content": updated_content,
        }),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["response"]["content"] == updated_content

    updated_entry = WidgetHighlights.objects(view_id=UUID(view_id), index=0, created_at=created_at).first()
    assert updated_entry.content == updated_content


def test_update_highlight_should_forbid_non_creator(flask_client):
    view_id = str(uuid4())
    created_at = datetime.now(UTC)
    creator_id = uuid4()  # Different from the logged-in user
    original_content = "Original content"
    malicious_content = "Malicious update"

    highlight_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=created_at,
        creator_id=creator_id,
        content=original_content,
        completed=None,
        comments_count=0,
        archived_at=datetime.fromtimestamp(0, tz=UTC),
    )
    highlight_entry.save()

    response = flask_client.post(
        "/api/v1/views/widgets/highlights/update",
        data=json.dumps({
            "view_id": view_id,
            "index": 0,
            "created_at": created_at.timestamp(),
            "content": malicious_content,
        }),
        content_type="application/json",
    )
    assert response.status_code == 200, response.text
    assert response.json["status"] == "error"
    assert response.json["response"]["exception"] == "Forbidden"

    unchanged_entry = WidgetHighlights.objects(view_id=UUID(view_id), index=0, created_at=created_at).first()
    assert unchanged_entry.content == original_content


def test_set_completed_should_update_completed_status(flask_client):
    view_id = str(uuid4())
    created_at = datetime.now(UTC)
    action_item_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=created_at,
        creator_id=g.user.id,
        content="Test action item",
        completed=False,
        comments_count=0,
    )
    action_item_entry.save()

    # Set completed to True
    response = flask_client.post(
        "/api/v1/views/widgets/highlights/set_completed",
        data=json.dumps({
            "view_id": view_id,
            "index": 0,
            "created_at": created_at.timestamp(),
            "completed": True
        }),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["response"]["completed"] is True

    # Set completed to False
    response = flask_client.post(
        "/api/v1/views/widgets/highlights/set_completed",
        data=json.dumps({
            "view_id": view_id,
            "index": 0,
            "created_at": created_at.timestamp(),
            "completed": False
        }),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json["response"]["completed"] is False


def test_set_completed_should_not_work_for_highlight(flask_client):
    view_id = str(uuid4())
    created_at = datetime.now(UTC)
    highlight_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=created_at,
        creator_id=g.user.id,
        content="Test highlight",
        completed=None,
        comments_count=0,
    )
    highlight_entry.save()

    response = flask_client.post(
        "/api/v1/views/widgets/highlights/set_completed",
        data=json.dumps({
            "view_id": view_id,
            "index": 0,
            "created_at": created_at.timestamp(),
            "completed": True
        }),
        content_type="application/json",
    )
    assert response.status_code == 200, response.text
    assert response.json["status"] == "error"
    assert response.json["response"]["exception"] == "NotFound"


@patch("argus.backend.controller.views_widgets.highlights.HighlightsService.send_action_notification")
def test_set_assignee_should_set_assignee_for_action_item(notification, flask_client):
    view_id = str(uuid4())
    created_at = datetime.now(UTC)
    action_item_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=created_at,
        creator_id=g.user.id,
        content="Test action item",
        completed=False,
        comments_count=0,
    )
    action_item_entry.save()

    new_assignee_id = str(uuid4())

    response = flask_client.post(
        "/api/v1/views/widgets/highlights/set_assignee",
        data=json.dumps({
            "view_id": view_id,
            "index": 0,
            "created_at": created_at.timestamp(),
            "assignee_id": new_assignee_id
        }),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["response"]["assignee_id"] == new_assignee_id
    assert notification.call_count == 1

    updated_entry = WidgetHighlights.objects(view_id=UUID(view_id), index=0, created_at=created_at).first()
    assert str(updated_entry.assignee_id) == new_assignee_id


def test_set_assignee_should_not_work_for_highlight(flask_client):
    view_id = str(uuid4())
    created_at = datetime.now(UTC)
    highlight_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=created_at,
        creator_id=g.user.id,
        content="Test highlight",
        completed=None,
        comments_count=0,
    )
    highlight_entry.save()

    new_assignee_id = str(uuid4())

    response = flask_client.post(
        "/api/v1/views/widgets/highlights/set_assignee",
        data=json.dumps({
            "view_id": view_id,
            "index": 0,
            "created_at": created_at.timestamp(),
            "assignee_id": new_assignee_id
        }),
        content_type="application/json",
    )
    assert response.status_code == 200, response.text
    assert response.json["status"] == "error"
    assert response.json["response"]["exception"] == "NotFound"


@patch("argus.backend.service.views_widgets.highlights.HighlightsService._send_highlight_notifications")
def test_create_comment_should_increment_comments_count(notification, flask_client):
    view_id = str(uuid4())
    highlight_created_at = datetime.now(UTC)
    highlight_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=highlight_created_at,
        creator_id=g.user.id,
        content="Test highlight",
        completed=None,
        comments_count=0,
    )
    highlight_entry.save()

    response = flask_client.post(
        "/api/v1/views/widgets/highlights/comments/create",
        data=json.dumps({
            "view_id": view_id,
            "index": 0,
            "highlight_created_at": highlight_created_at.timestamp(),
            "content": "Test comment",
        }),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["response"]["content"] == "Test comment"

    updated_highlight = WidgetHighlights.objects(view_id=UUID(
        view_id), index=0, created_at=highlight_created_at).first()
    assert updated_highlight.comments_count == 1


def test_delete_comment_should_decrement_comments_count(flask_client):
    view_id = str(uuid4())
    highlight_created_at = datetime.now(UTC)
    comment_created_at = datetime.now(UTC)
    highlight_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=highlight_created_at,
        creator_id=g.user.id,
        content="Test highlight",
        completed=None,
        comments_count=1,
    )
    highlight_entry.save()
    comment_entry = WidgetComment(
        view_id=UUID(view_id),
        index=0,
        highlight_at=highlight_created_at,
        created_at=comment_created_at,
        creator_id=g.user.id,
        content="Test comment",
    )
    comment_entry.save()

    response = flask_client.post(
        "/api/v1/views/widgets/highlights/comments/delete",
        data=json.dumps({
            "view_id": view_id,
            "index": 0,
            "highlight_created_at": highlight_created_at.timestamp(),
            "created_at": comment_created_at.timestamp(),
        }),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json["status"] == "ok"

    updated_highlight = WidgetHighlights.objects(view_id=UUID(
        view_id), index=0, created_at=highlight_created_at).first()
    assert updated_highlight.comments_count == 0


@patch("argus.backend.service.views_widgets.highlights.HighlightsService._send_highlight_notifications")
def test_update_comment_should_modify_content(notification, flask_client):
    view_id = str(uuid4())
    highlight_created_at = datetime.now(UTC)
    comment_created_at = datetime.now(UTC)
    comment_content = "Original comment"
    updated_content = "Updated comment"

    highlight_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=highlight_created_at,
        creator_id=g.user.id,
        content="Test highlight",
        completed=None,
        comments_count=1,
    )
    highlight_entry.save()
    comment_entry = WidgetComment(
        view_id=UUID(view_id),
        index=0,
        highlight_at=highlight_created_at,
        created_at=comment_created_at,
        creator_id=g.user.id,
        content=comment_content,
    )
    comment_entry.save()

    response = flask_client.post(
        "/api/v1/views/widgets/highlights/comments/update",
        data=json.dumps({
            "view_id": view_id,
            "index": 0,
            "highlight_created_at": highlight_created_at.timestamp(),
            "created_at": comment_created_at.timestamp(),
            "content": updated_content,
        }),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["response"]["content"] == updated_content


def test_get_comments_should_return_list_of_comments(flask_client):
    view_id = str(uuid4())
    highlight_created_at = datetime.now(UTC)
    comment_created_at = datetime.now(UTC)
    highlight_entry = WidgetHighlights(
        view_id=UUID(view_id),
        index=0,
        created_at=highlight_created_at,
        creator_id=g.user.id,
        content="Test highlight",
        completed=None,
        comments_count=1,
    )
    highlight_entry.save()
    comment_entry = WidgetComment(
        view_id=UUID(view_id),
        index=0,
        highlight_at=highlight_created_at,
        created_at=comment_created_at,
        creator_id=g.user.id,
        content="Test comment",
    )
    comment_entry.save()

    response = flask_client.get(
        f"/api/v1/views/widgets/highlights/comments?view_id={view_id}&index=0&created_at={highlight_created_at.timestamp()}")
    assert response.status_code == 200
    assert response.json["status"] == "ok"
    comments = response.json["response"]
    assert len(comments) == 1
    assert comments[0]["content"] == "Test comment"
