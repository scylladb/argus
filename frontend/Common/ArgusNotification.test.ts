import { describe, it, expect } from "vitest";
import {
    ArgusNotification,
    ArgusShortSummary,
    NotificationsState,
    NotificationTypes,
    NotificationSource,
} from "./ArgusNotification";
import type { ArgusNotificationJSON, ArgusShortSummaryJSON } from "./ArgusNotification";

describe("ArgusNotification", () => {
    const sampleJSON: ArgusNotificationJSON = {
        receiver: "user-1",
        sender: "user-2",
        created: 1710504000000, // 2024-03-15T12:00:00Z
        id: "notif-1",
        type: NotificationTypes.Mention,
        state: NotificationsState.UNREAD,
        source: NotificationSource.Comment,
        source_id: "comment-42",
        title: "You were mentioned",
        content: "@user-1 check this out",
    };

    it("creates an instance from JSON with correct field mapping", () => {
        const notif = ArgusNotification.from_json(sampleJSON);

        expect(notif.receiver).toBe("user-1");
        expect(notif.sender).toBe("user-2");
        expect(notif.id).toBe("notif-1");
        expect(notif.type).toBe(NotificationTypes.Mention);
        expect(notif.state).toBe(NotificationsState.UNREAD);
        expect(notif.source).toBe(NotificationSource.Comment);
        expect(notif.sourceId).toBe("comment-42");
        expect(notif.title).toBe("You were mentioned");
        expect(notif.content).toBe("@user-1 check this out");
    });

    it("converts created timestamp to a Date object", () => {
        const notif = ArgusNotification.from_json(sampleJSON);
        expect(notif.date).toBeInstanceOf(Date);
        expect(notif.date.toISOString()).toBe("2024-03-15T12:00:00.000Z");
    });

    it("maps source_id to sourceId (snake_case to camelCase)", () => {
        const notif = ArgusNotification.from_json(sampleJSON);
        expect(notif.sourceId).toBe(sampleJSON.source_id);
    });
});

describe("ArgusShortSummary", () => {
    const sampleJSON: ArgusShortSummaryJSON = {
        receiver: "user-A",
        sender: "user-B",
        created: 1710590400000, // 2024-03-16T12:00:00Z
        id: "summary-1",
        state: NotificationsState.READ,
        title: "Status changed",
    };

    it("creates an instance from JSON with correct fields", () => {
        const summary = ArgusShortSummary.from_json(sampleJSON);

        expect(summary.receiver).toBe("user-A");
        expect(summary.sender).toBe("user-B");
        expect(summary.id).toBe("summary-1");
        expect(summary.state).toBe(NotificationsState.READ);
        expect(summary.title).toBe("Status changed");
    });

    it("converts created timestamp to a Date object", () => {
        const summary = ArgusShortSummary.from_json(sampleJSON);
        expect(summary.date).toBeInstanceOf(Date);
        expect(summary.date.toISOString()).toBe("2024-03-16T12:00:00.000Z");
    });
});

describe("Enum values", () => {
    it("NotificationsState has expected values", () => {
        expect(NotificationsState.UNREAD).toBe(1);
        expect(NotificationsState.READ).toBe(2);
        expect(NotificationsState.DEFAULT).toBe(999);
    });

    it("NotificationTypes has expected values", () => {
        expect(NotificationTypes.Mention).toBe("TYPE_MENTION");
        expect(NotificationTypes.StatusChange).toBe("TYPE_STATUS_CHANGE");
        expect(NotificationTypes.AssigneeChange).toBe("TYPE_ASSIGNEE_CHANGE");
        expect(NotificationTypes.ScheduleChange).toBe("TYPE_SCHEDULE_CHANGE");
    });

    it("NotificationSource has expected values", () => {
        expect(NotificationSource.Comment).toBe("COMMENT");
        expect(NotificationSource.TestRun).toBe("TEST_RUN");
        expect(NotificationSource.ViewActionItem).toBe("VIEW_ACTION_ITEM");
        expect(NotificationSource.ViewHighlight).toBe("VIEW_HIGHLIGHT");
    });
});
