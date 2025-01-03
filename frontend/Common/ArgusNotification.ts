export enum NotificationsState {
    UNREAD = 1,
    READ = 2,
    DEFAULT = 999,
}

export enum NotificationTypes {
    Mention = "TYPE_MENTION",
    StatusChange = "TYPE_STATUS_CHANGE",
    AssigneeChange = "TYPE_ASSIGNEE_CHANGE",
    ScheduleChange = "TYPE_SCHEDULE_CHANGE",
    DEFAULT = "",
}

export enum NotificationSource {
    Comment = "COMMENT",
    TestRun = "TEST_RUN",
    ViewActionItem = "VIEW_ACTION_ITEM",
    ViewHighlight = "VIEW_HIGHLIGHT",
}

export interface ArgusNotificationJSON {
    receiver: string
    sender: string
    created: number
    id: string
    type: NotificationTypes
    state: NotificationsState
    source: NotificationSource
    source_id: string
    title: string
    content: string
}

export interface ArgusShortSummaryJSON {
    receiver: string
    sender: string
    created: number
    id: string
    state: NotificationsState
    title: string
}

export class ArgusNotification {
    receiver: string
    sender: string
    date: Date
    id: string
    type: NotificationTypes
    state: NotificationsState
    source: NotificationSource
    sourceId: string
    title: string
    content: string

    constructor(receiver: string, sender: string, created: number, id: string, type: NotificationTypes,
        state: NotificationsState, source: NotificationSource, sourceId: string, title: string, content: string) {
        this.receiver = receiver;
        this.sender = sender;
        this.date = new Date(created);
        this.id = id;
        this.type = type;
        this.state = state;
        this.source = source;
        this.sourceId = sourceId;
        this.title = title;
        this.content = content;
    }

    static from_json(obj: ArgusNotificationJSON) {
        return new ArgusNotification(obj.receiver, obj.sender, obj.created, obj.id,
            obj.type, obj.state, obj.source, obj.source_id, obj.title, obj.content);
    }
}

export class ArgusShortSummary {
    receiver: string
    sender: string
    date: Date
    id: string
    state: NotificationsState
    title: string

    constructor(receiver: string, sender: string, created: number, id: string,
        state: NotificationsState, title: string,) {
        this.receiver = receiver;
        this.sender = sender;
        this.date = new Date(created);
        this.id = id;
        this.state = state;
        this.title = title;
    }

    static from_json(obj: ArgusShortSummaryJSON) {
        return new ArgusShortSummary(obj.receiver, obj.sender, obj.created, obj.id,
            obj.state, obj.title);
    }
}
