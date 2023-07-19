from datetime import datetime
import json
from argus.backend.models.web import ArgusEvent, ArgusEventTypes


class EventService:
    @staticmethod
    def create_run_event(kind: ArgusEventTypes, body: dict, user_id=None, run_id=None, release_id=None, group_id=None, test_id=None):
        event = ArgusEvent()
        event.release_id = release_id
        event.group_id = group_id
        event.test_id = test_id
        event.user_id = user_id
        event.run_id = run_id
        event.body = json.dumps(body, ensure_ascii=True, separators=(',', ':'))
        event.kind = kind.value
        event.created_at = datetime.utcnow()
        event.save()
