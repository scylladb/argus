import { describe, it, expect } from "vitest";
import {
    DEFAULT_SORT,
    EMPTY_FILTERS,
    descriptionSummary,
    endTimeLabel,
    filterNemeses,
    isFiltering,
    nemesisKey,
    nemesisMatches,
    nemesisStatuses,
    nextSort,
    reasonLabel,
    sortNemeses,
    statusClasses,
    statusLabel,
} from "./nemesisListing";
import type { NemesisInfo } from "./types";

const T0 = Date.UTC(2026, 9, 20, 10, 0, 0) / 1000;

const nemesis = (overrides: Partial<NemesisInfo> = {}): NemesisInfo => ({
    class_name: "DisruptRestartNodeMonkey",
    name: "disrupt_restart_node",
    description: "Restart (hard) the target node.\n\nWaits for the node to rejoin.",
    duration: 90,
    target_node: { name: "db-node-1", ip: "1.2.3.4", shards: 8 },
    status: "succeeded",
    start_time: T0,
    end_time: T0 + 90,
    stack_trace: "",
    ...overrides,
});

describe("sortNemeses", () => {
    it("orders by start time, newest first, by default", () => {
        const items = [
            nemesis({ name: "a", start_time: T0 }),
            nemesis({ name: "b", start_time: T0 + 200 }),
            nemesis({ name: "c", start_time: T0 + 100 }),
        ];

        expect(sortNemeses(items, DEFAULT_SORT).map((n) => n.name)).toEqual(["b", "c", "a"]);
    });

    it("orders names and node names with numeric awareness", () => {
        const items = [
            nemesis({ name: "disrupt_10", target_node: { name: "db-node-10", ip: null, shards: null } }),
            nemesis({ name: "disrupt_2", target_node: { name: "db-node-2", ip: null, shards: null } }),
        ];

        expect(sortNemeses(items, { key: "name", direction: "asc" }).map((n) => n.name)).toEqual(["disrupt_2", "disrupt_10"]);
        expect(sortNemeses(items, { key: "node", direction: "asc" }).map((n) => n.target_node.name))
            .toEqual(["db-node-2", "db-node-10"]);
        expect(sortNemeses(items, { key: "node", direction: "desc" }).map((n) => n.target_node.name))
            .toEqual(["db-node-10", "db-node-2"]);
    });

    it("sorts an unfinished nemesis as the latest end time", () => {
        const items = [
            nemesis({ name: "running", end_time: 0 }),
            nemesis({ name: "done", end_time: T0 + 500 }),
        ];

        expect(sortNemeses(items, { key: "end_time", direction: "desc" }).map((n) => n.name)).toEqual(["running", "done"]);
        expect(sortNemeses(items, { key: "end_time", direction: "asc" }).map((n) => n.name)).toEqual(["done", "running"]);
    });

    it("breaks a status tie by start time", () => {
        const items = [
            nemesis({ name: "late", status: "failed", start_time: T0 + 100 }),
            nemesis({ name: "early", status: "failed", start_time: T0 }),
            nemesis({ name: "ok", status: "succeeded", start_time: T0 + 50 }),
        ];

        expect(sortNemeses(items, { key: "status", direction: "asc" }).map((n) => n.name)).toEqual(["early", "late", "ok"]);
    });

    it("leaves the input array untouched", () => {
        const items = [nemesis({ name: "b" }), nemesis({ name: "a" })];

        sortNemeses(items, { key: "name", direction: "asc" });

        expect(items.map((n) => n.name)).toEqual(["b", "a"]);
    });
});

describe("nextSort", () => {
    it("flips the direction when the active column is clicked again", () => {
        expect(nextSort({ key: "name", direction: "asc" }, "name")).toEqual({ key: "name", direction: "desc" });
        expect(nextSort({ key: "name", direction: "desc" }, "name")).toEqual({ key: "name", direction: "asc" });
    });

    it("switches to the default direction of the new column", () => {
        expect(nextSort({ key: "start_time", direction: "asc" }, "name")).toEqual({ key: "name", direction: "asc" });
        expect(nextSort({ key: "name", direction: "asc" }, "end_time")).toEqual({ key: "end_time", direction: "desc" });
    });
});

describe("nemesisMatches", () => {
    it("keeps every nemesis for a blank filter", () => {
        expect(nemesisMatches(nemesis(), "")).toBe(true);
        expect(nemesisMatches(nemesis(), "   ")).toBe(true);
    });

    it("matches the name, class, node, status, start time, In progress and description", () => {
        const running = nemesis({ end_time: 0 });

        expect(nemesisMatches(running, "restart_node")).toBe(true);
        expect(nemesisMatches(running, "DisruptRestartNodeMonkey")).toBe(true);
        expect(nemesisMatches(running, "db-node-1")).toBe(true);
        expect(nemesisMatches(running, "Succeeded")).toBe(true);
        expect(nemesisMatches(running, "2026-10-20 10:00:00")).toBe(true);
        expect(nemesisMatches(running, "In progress")).toBe(true);
        expect(nemesisMatches(running, "rejoin")).toBe(true);
        expect(nemesisMatches(running, "no such text")).toBe(false);
    });

    it("matches as a case-insensitive regular expression", () => {
        expect(nemesisMatches(nemesis(), "^DISRUPT_(restart|stop)")).toBe(true);
        expect(nemesisMatches(nemesis(), "^stop")).toBe(false);
    });

    it("falls back to a substring match when the regular expression is invalid", () => {
        expect(nemesisMatches(nemesis(), "(hard")).toBe(true);
        expect(nemesisMatches(nemesis(), "(soft")).toBe(false);
    });

    it("filters a list by text", () => {
        const items = [nemesis({ name: "disrupt_restart_node" }), nemesis({ name: "disrupt_stop_node" })];

        expect(filterNemeses(items, { ...EMPTY_FILTERS, text: "stop" }).map((n) => n.name)).toEqual(["disrupt_stop_node"]);
    });

    it("filters a list by node and by status, combined with the text", () => {
        const items = [
            nemesis({ name: "a", status: "failed", target_node: { name: "db-node-1", ip: null, shards: null } }),
            nemesis({ name: "b", status: "succeeded", target_node: { name: "db-node-1", ip: null, shards: null } }),
            nemesis({ name: "c", status: "failed", target_node: { name: "db-node-2", ip: null, shards: null } }),
        ];

        expect(filterNemeses(items, { ...EMPTY_FILTERS, node: "db-node-1" }).map((n) => n.name)).toEqual(["a", "b"]);
        expect(filterNemeses(items, { ...EMPTY_FILTERS, status: "failed" }).map((n) => n.name)).toEqual(["a", "c"]);
        expect(filterNemeses(items, { text: "^a|^c", node: "db-node-1", status: "failed" }).map((n) => n.name)).toEqual(["a"]);
    });

    it("tells whether any filter is active", () => {
        expect(isFiltering(EMPTY_FILTERS)).toBe(false);
        expect(isFiltering({ ...EMPTY_FILTERS, text: "  " })).toBe(false);
        expect(isFiltering({ ...EMPTY_FILTERS, node: "db-node-1" })).toBe(true);
        expect(isFiltering({ ...EMPTY_FILTERS, status: "failed" })).toBe(true);
    });

    it("lists the statuses present, sorted", () => {
        const items = [nemesis({ status: "succeeded" }), nemesis({ status: "failed" }), nemesis({ status: "succeeded" })];

        expect(nemesisStatuses(items)).toEqual(["failed", "succeeded"]);
    });
});

describe("labels", () => {
    it("keys a nemesis by its start time and name", () => {
        expect(nemesisKey(nemesis({ name: "a", start_time: 5 }))).toBe("5:a");
    });

    it("returns the first non-empty line of the description, trimmed", () => {
        expect(descriptionSummary("\n   Restart the node.  \n\nMore.")).toBe("Restart the node.");
    });

    it("returns an empty summary for a missing description", () => {
        expect(descriptionSummary(null)).toBe("");
        expect(descriptionSummary(undefined)).toBe("");
        expect(descriptionSummary("  \n ")).toBe("");
    });

    it("title-cases a known status and does not throw on an empty one", () => {
        expect(statusLabel("succeeded")).toBe("Succeeded");
        expect(statusLabel("")).toBe("Unknown");
    });

    it("pairs the background and the text colour, with a fallback for an unknown status", () => {
        expect(statusClasses("failed")).toBe("bg-danger text-light");
        expect(statusClasses("terminated")).toBe("bg-secondary text-light");
        expect(statusClasses("mystery")).toBe("bg-secondary text-light");
    });

    it("labels the end time", () => {
        expect(endTimeLabel(nemesis({ end_time: 0 }))).toBe("In progress");
        expect(endTimeLabel(nemesis({ end_time: T0 + 90 }))).toBe("2026-10-20 10:01:30");
    });

    it("labels the reason by status", () => {
        expect(reasonLabel("skipped")).toBe("Skip reason");
        expect(reasonLabel("failed")).toBe("Failure reason");
        expect(reasonLabel("succeeded")).toBe("Message");
    });
});
