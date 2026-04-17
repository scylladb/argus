import { describe, it, expect } from "vitest";
import { getAssigneesForTest, shouldFilterOutByUser } from "./TestDashboard.svelte";

describe("getAssigneesForTest", () => {
    const assigneeList = {
        tests: {
            "test-1": ["alice", "bob"],
            "test-2": [],
        },
        groups: {
            "group-a": ["charlie"],
            "group-b": [],
        },
    };

    it("merges test and group assignees", () => {
        const result = getAssigneesForTest(assigneeList, "test-1", "group-a", []);
        expect(result).toEqual(["alice", "bob", "charlie"]);
    });

    it("returns only test assignees when group has none", () => {
        const result = getAssigneesForTest(assigneeList, "test-1", "group-b", []);
        expect(result).toEqual(["alice", "bob"]);
    });

    it("returns only group assignees when test has none", () => {
        const result = getAssigneesForTest(assigneeList, "test-2", "group-a", []);
        expect(result).toEqual(["charlie"]);
    });

    it("falls back to lastRun.assignee when not already in the list", () => {
        const lastRuns = [{ assignee: "dave" }];
        const result = getAssigneesForTest(assigneeList, "test-2", "group-b", lastRuns);
        expect(result).toEqual(["dave"]);
    });

    it("keeps merged list when lastRun.assignee is already present", () => {
        const lastRuns = [{ assignee: "alice" }];
        const result = getAssigneesForTest(assigneeList, "test-1", "group-a", lastRuns);
        expect(result).toEqual(["alice", "bob", "charlie"]);
    });

    it("handles missing test/group keys gracefully", () => {
        const result = getAssigneesForTest(assigneeList, "unknown", "unknown", []);
        expect(result).toEqual([]);
    });

    it("handles null assigneeList fields", () => {
        const result = getAssigneesForTest({}, "test-1", "group-a", []);
        expect(result).toEqual([]);
    });

    it("handles null/undefined last_runs", () => {
        const result = getAssigneesForTest(assigneeList, "test-1", "group-a", null);
        expect(result).toEqual(["alice", "bob", "charlie"]);
    });
});

describe("shouldFilterOutByUser", () => {
    const assigneeList = {
        tests: { t1: ["user-1"] },
        groups: { g1: ["user-1"] },
    };

    it("returns false when user is null/undefined (no filtering)", () => {
        expect(shouldFilterOutByUser(assigneeList, null, {})).toBe(false);
        expect(shouldFilterOutByUser(assigneeList, undefined, {})).toBe(false);
    });

    it("returns false for unknown type", () => {
        const user = { id: "user-1" };
        expect(shouldFilterOutByUser(assigneeList, user, {}, undefined, undefined, "unknown")).toBe(false);
    });

    it("filters by group type when group has no matching assignee and no child tests match", () => {
        const emptyAssigneeList = { tests: {}, groups: {} };
        const user = { id: "user-1" };
        const group = { id: "g-empty" };
        const tests: any[] = [];
        const result = shouldFilterOutByUser(emptyAssigneeList, user, null, group, tests, "group");
        expect(result).toBe(true);
    });

    it("does not filter group when group assignee matches user", () => {
        const user = { id: "user-1" };
        const group = { id: "g1" };
        const result = shouldFilterOutByUser(assigneeList, user, null, group, [], "group");
        expect(result).toBe(false);
    });
});
