import { describe, expect, it } from "vitest";
import { allStatuses, barSegments, shortVersion, gridRows, issueVersions, matchesFilter, onlyStatus, showsAll, statusGroup, updatedAgo } from "./summaryUtils";
import type { Summary, SummaryCounts, SummaryFamily, SummaryIssue, SummaryTest } from "./types";

const counts = (overrides: Partial<SummaryCounts> = {}): SummaryCounts => ({
    executed: 0, passed: 0, failed: 0, aborted: 0, in_progress: 0, pending: 0,
    issues_new: 0, issues_existing: 0, issues_fixed: 0, ...overrides,
});

const entry = (name: string, status: string, version: string | null, group = "Group"): SummaryTest => ({
    test_id: name, group_id: "g", test_name: name, group_name: group, status,
    run_id: version ? `run-${name}-${version}` : null, build_id: version ? `job/${name}` : null,
    build_number: version ? 1 : null, version,
});

const summary = (version: string | null, tests: SummaryTest[], issueIds: string[] = []): Summary => ({
    version, counts: counts(), tests,
    issues: issueIds.map((id) => ({ id, type: "jira", key: id, title: null, url: null, state: "open", novelty: "new",
                                    status: "open", test_ids: [], run_ids: [],
                                    issue: { id, subtype: "jira" } as SummaryIssue["issue"] })),
});

const FAMILY: SummaryFamily = {
    family: "2025.1.0",
    rollup: summary(null, [entry("b-upgrade", "passed", "2025.1.0~rc1"), entry("a-gemini", "failed", "2025.1.0~rc1"),
                           entry("c-longevity", "pending", null)], ["SCYLLADB-1"]),
    versions: [
        summary("2025.1.0~rc0", [entry("b-upgrade", "failed", "2025.1.0~rc0")], ["SCYLLADB-1"]),
        summary("2025.1.0~rc1", [entry("b-upgrade", "passed", "2025.1.0~rc1"), entry("a-gemini", "test_error", "2025.1.0~rc1"),
                                 entry("c-longevity", "pending", null)]),
    ],
};

describe("statusGroup", () => {
    it("folds the run statuses into the summary groups", () => {
        expect(statusGroup("passed")).toBe("passed");
        expect(["failed", "test_error", "error"].map(statusGroup)).toEqual(["failed", "failed", "failed"]);
        expect(statusGroup("aborted")).toBe("aborted");
        expect(["created", "running"].map(statusGroup)).toEqual(["in_progress", "in_progress"]);
        expect(statusGroup("pending")).toBe("pending");
    });

    it("matches a status when its group is switched on", () => {
        expect(matchesFilter("test_error", allStatuses())).toBe(true);
        expect(matchesFilter("test_error", onlyStatus("failed"))).toBe(true);
        expect(matchesFilter("passed", onlyStatus("failed"))).toBe(false);
        expect(matchesFilter("passed", { ...allStatuses(), failed: false })).toBe(true);
    });

    it("knows when every group is on", () => {
        expect(showsAll(allStatuses())).toBe(true);
        expect(showsAll({ ...allStatuses(), aborted: false })).toBe(false);
    });
});

describe("barSegments", () => {
    it("gives each non-empty group its share of the bar, in a fixed order", () => {
        const segments = barSegments(counts({ passed: 3, failed: 1, pending: 4 }));

        expect(segments.map((segment) => [segment.group, segment.count, segment.percent])).toEqual([
            ["passed", 3, 37.5], ["failed", 1, 12.5], ["pending", 4, 50]]);
    });

    it("is empty when nothing counts", () => {
        expect(barSegments(counts())).toEqual([]);
    });
});

describe("updatedAgo", () => {
    const now = new Date("2026-11-05T10:00:00Z");

    it("says just now under a minute and humanizes anything older", () => {
        expect(updatedAgo("2026-11-05T09:59:30+00:00", now)).toBe("just now");
        expect(updatedAgo("2026-11-05T09:57:00+00:00", now)).toBe("3 minutes ago");
        expect(updatedAgo("2026-11-04T10:00:00+00:00", now)).toBe("1 day ago");
    });

    it("is empty without a time", () => {
        expect(updatedAgo(null, now)).toBe("");
    });
});

describe("shortVersion", () => {
    it("names a version by its suffix inside its family", () => {
        expect(shortVersion("2025.1.0~rc2")).toBe("rc2");
        expect(shortVersion("2025.1.0~dev")).toBe("dev");
        expect(shortVersion("2025.1.0")).toBe("final");
    });
});

describe("issueVersions", () => {
    it("lists the versions each issue reproduced on, in version order", () => {
        expect(issueVersions(FAMILY)).toEqual({ "SCYLLADB-1": ["2025.1.0~rc0"] });
    });
});

describe("gridRows", () => {
    it("gives one row per family test, sorted by group and name, with a cell per version", () => {
        const rows = gridRows(FAMILY, allStatuses());

        expect(rows.map((row) => row.test.test_name)).toEqual(["a-gemini", "b-upgrade", "c-longevity"]);
        expect(rows[1].cells.map((cell) => cell?.status ?? null)).toEqual(["failed", "passed"]);
        expect(rows[0].cells.map((cell) => cell?.status ?? null)).toEqual([null, "test_error"]);
    });

    it("keeps the rows whose family result is in the filter", () => {
        expect(gridRows(FAMILY, onlyStatus("failed")).map((row) => row.test.test_name)).toEqual(["a-gemini"]);
        expect(gridRows(FAMILY, { ...allStatuses(), passed: false }).map((row) => row.test.test_name)).toEqual(
            ["a-gemini", "c-longevity"]);
    });
});
