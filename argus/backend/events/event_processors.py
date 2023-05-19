from argus.backend.models.web import ArgusEventTypes


def event_process_posted_comment(event: dict) -> dict:
    return event["message"].format(**event)


def event_process_status_changed(event: dict) -> dict:
    return event["message"].format(**event)


def event_process_investigation_status_changed(event: dict) -> dict:
    return event["message"].format(**event)


def event_process_assignee_changed(event: dict) -> dict:
    return event["message"].format(**event)


def event_process_issue_added(event: dict) -> dict:
    return event["message"].format(**event)


EVENT_PROCESSORS = {
    ArgusEventTypes.AssigneeChanged: event_process_assignee_changed,
    ArgusEventTypes.TestRunStatusChanged: event_process_status_changed,
    ArgusEventTypes.TestRunCommentPosted: event_process_posted_comment,
    ArgusEventTypes.TestRunCommentUpdated: event_process_posted_comment,
    ArgusEventTypes.TestRunCommentDeleted: event_process_posted_comment,
    ArgusEventTypes.TestRunIssueAdded: event_process_issue_added,
    ArgusEventTypes.TestRunIssueRemoved: event_process_issue_added,
    ArgusEventTypes.TestRunInvestigationStatusChanged: event_process_investigation_status_changed,
    ArgusEventTypes.TestRunBatchInvestigationStatusChange: event_process_investigation_status_changed,
}
