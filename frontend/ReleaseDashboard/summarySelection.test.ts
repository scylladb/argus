import { describe, it, expect } from "vitest";
import { summaryTestSelection } from "./summarySelection";
import type { SummaryTest } from "../Views/Widgets/ReleaseSummary/types";

const summaryTest = (overrides: Partial<SummaryTest> = {}): SummaryTest => ({
    test_id: "t1",
    group_id: "g1",
    test_name: "longevity-test",
    group_name: "Longevity",
    status: "failed",
    run_id: "r1",
    build_id: "scylla-master/longevity-test",
    build_number: 12,
    version: "2025.1.0",
    start_time: "2025-11-01T10:00:00Z",
    ...overrides,
});

describe("summaryTestSelection", () => {
    it("takes the dashboard entry when the dashboard holds the test", () => {
        const lastRuns = [{ id: "r9" }];
        const stats = {
            groups: {
                g1: {
                    group: { name: "Longevity tests" },
                    tests: {
                        t1: {
                            test: { id: "t1", name: "longevity-dash", build_system_id: "job/path" },
                            status: "passed",
                            start_time: 1700000000,
                            last_runs: lastRuns,
                        },
                    },
                },
            },
        };

        const selection = summaryTestSelection(stats, summaryTest());

        expect(selection).toEqual({
            name: "longevity-dash", id: "t1", assignees: [], group: "Longevity tests", status: "passed",
            start_time: 1700000000, last_runs: lastRuns, build_system_id: "job/path",
        });
    });

    it("builds the selection from the summary when the dashboard lacks the test", () => {
        const selection = summaryTestSelection({ groups: {} }, summaryTest());

        expect(selection.name).toBe("longevity-test");
        expect(selection.group).toBe("Longevity");
        expect(selection.start_time).toBe(Date.parse("2025-11-01T10:00:00Z") / 1000);
        expect(selection.last_runs).toEqual([expect.objectContaining({ id: "r1", build_number: 12 })]);
        expect(selection.build_system_id).toBe("scylla-master/longevity-test");
    });

    it("selects a test without a run with no runs", () => {
        const selection = summaryTestSelection(undefined, summaryTest({ run_id: null, start_time: null }));

        expect(selection.start_time).toBe(0);
        expect(selection.last_runs).toEqual([]);
    });
});
