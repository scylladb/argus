import logging
from uuid import UUID
from flask import render_template
from argus.db.models import ArgusNotification, ArgusNotificationSourceTypes, ArgusNotificationTypes, ArgusNotificationState, User

LOGGER = logging.getLogger(__name__)


class NotificationManagerException(Exception):
    pass


class NotificationManagerService:
    NOTIFICATION_TITLES = {
        ArgusNotificationTypes.Mention: "You were mentioned in a comment",
        ArgusNotificationTypes.StatusChange: "A run you are assigned to changed status",
        ArgusNotificationTypes.AssigneeChange: "You were assigned to a run",
        ArgusNotificationTypes.ScheduleChange: "You were assigned to a schedule",
    }

    CONTENT_TEMPLATES = {
        ArgusNotificationTypes.Mention: lambda p: render_template("notifications/mention.html.j2", **p if p else {})
    }

    def __init__(self) -> None:
        pass

    def _check_user(self, user_id: UUID) -> bool:
        try:
            user = User.get(id=user_id)
            if user.id == user_id:
                return True
        except User.DoesNotExist:
            return False

    def _get_title_for_notification_type(self, notification_type: ArgusNotificationTypes) -> str:
        if title := self.NOTIFICATION_TITLES.get(notification_type):
            return title
        raise NotificationManagerException(
            f"Title for notification type {notification_type} not found.", notification_type)

    def _render_content(self, content_type: ArgusNotificationTypes, params: dict):
        if content_renderer := self.CONTENT_TEMPLATES.get(content_type):
            return content_renderer(params)
        raise NotificationManagerException(
            f"Content renderer for notification type {content_type} not found.", content_type)

    def send_notification(self, receiver: UUID, sender: UUID, notification_type: ArgusNotificationTypes, source_type: ArgusNotificationSourceTypes,
                          source_id: UUID, title: str = None, content: str = None, content_params: dict = None) -> ArgusNotification:
        new_notification = ArgusNotification()
        for user in [sender, receiver]:
            if not self._check_user(user_id=user):
                raise NotificationManagerException(f"UserId {user} not found in the database", user)

        new_notification.sender = sender
        new_notification.receiver = receiver
        new_notification.type = notification_type.value
        new_notification.source_type = source_type.value
        new_notification.source_id = source_id
        new_notification.title = title if title else self._get_title_for_notification_type(notification_type)
        new_notification.content = content if content else self._render_content(notification_type, content_params)

        return new_notification.save()

    def get_notificaton(self, receiver: UUID, notification_id: UUID) -> ArgusNotification:
        return ArgusNotification.get(receiver=receiver, id=notification_id)

    def get_unread_count(self, receiver: UUID) -> int:
        query = ArgusNotification.filter(
            receiver=receiver, state__eq=ArgusNotificationState.UNREAD.value).allow_filtering().all()
        return len(query)

    def read_notification(self, receiver: UUID, notification_id: UUID) -> ArgusNotification:
        notification = ArgusNotification.get(receiver=receiver, id=notification_id)
        notification.state = ArgusNotificationState.READ
        return bool(notification.save().state)

    def get_notifications(self, receiver: UUID, limit: int = 20, after: UUID = None) -> list[ArgusNotification]:
        if after:
            return ArgusNotification.filter(receiver=receiver, id__lte=after).all().limit(limit)
        return ArgusNotification.filter(receiver=receiver).all().limit(limit)
