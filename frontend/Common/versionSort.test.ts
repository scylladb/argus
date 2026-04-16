import { describe, it, expect } from "vitest";
import { compareVersions } from "./versionSort";

describe("compareVersions", () => {
    describe("basic numeric ordering", () => {
        it("sorts simple versions numerically, not lexicographically", () => {
            expect(compareVersions("5.10", "5.9")).toBeGreaterThan(0);
            expect(compareVersions("5.2", "5.10")).toBeLessThan(0);
        });

        it("sorts three-segment versions", () => {
            expect(compareVersions("5.2.1", "5.2.0")).toBeGreaterThan(0);
            expect(compareVersions("5.2.1", "5.2.1")).toBe(0);
            expect(compareVersions("5.2.1", "5.3.0")).toBeLessThan(0);
        });

        it("sorts calendar-style versions", () => {
            expect(compareVersions("2025.1.3", "2024.2.9")).toBeGreaterThan(0);
        });
    });

    describe("pre-release ordering", () => {
        it("rc sorts before official release", () => {
            expect(compareVersions("5.2.1.rc1", "5.2.1")).toBeLessThan(0);
        });

        it("dev sorts before rc (lexicographic)", () => {
            expect(compareVersions("5.2.1.dev", "5.2.1.rc1")).toBeLessThan(0);
        });

        it("dev sorts before official release", () => {
            expect(compareVersions("5.2.1.dev", "5.2.1")).toBeLessThan(0);
        });

        it("handles tilde-separated pre-release (6.0.0~rc1)", () => {
            expect(compareVersions("6.0.0~rc1", "6.0.0")).toBeLessThan(0);
            expect(compareVersions("6.0.0~rc1", "6.0.0~rc2")).toBeLessThan(0);
        });
    });

    describe("build metadata stripping", () => {
        it("ignores build metadata after first dash", () => {
            expect(compareVersions("5.2.1-0.20240815.abc", "5.2.1")).toBe(0);
        });

        it("compares versions identically when only metadata differs", () => {
            expect(compareVersions("5.2.1-build1", "5.2.1-build2")).toBe(0);
        });
    });

    describe("different segment lengths", () => {
        it("shorter numeric version is less than longer", () => {
            expect(compareVersions("5.2", "5.2.1")).toBeLessThan(0);
        });

        it("equal versions return 0", () => {
            expect(compareVersions("5.2.1", "5.2.1")).toBe(0);
        });
    });

    describe("null/undefined/empty guards", () => {
        it("both null returns 0", () => {
            expect(compareVersions(null, null)).toBe(0);
        });

        it("both undefined returns 0", () => {
            expect(compareVersions(undefined, undefined)).toBe(0);
        });

        it("null sorts after any real version", () => {
            expect(compareVersions(null, "5.2.1")).toBeGreaterThan(0);
            expect(compareVersions("5.2.1", null)).toBeLessThan(0);
        });

        it("undefined sorts after any real version", () => {
            expect(compareVersions(undefined, "5.2.1")).toBeGreaterThan(0);
            expect(compareVersions("5.2.1", undefined)).toBeLessThan(0);
        });

        it("empty string sorts after any real version", () => {
            expect(compareVersions("", "5.2.1")).toBeGreaterThan(0);
            expect(compareVersions("5.2.1", "")).toBeLessThan(0);
        });
    });

    describe("full array sorting", () => {
        it("sorts a mixed array in correct ascending order", () => {
            const input = ["5.10.0", "5.9.0", "5.2.1.rc1", "5.2.1", "5.2.1.dev", "2024.1.3", "6.0.0~rc1", "6.0.0"];
            const sorted = [...input].sort(compareVersions);
            expect(sorted).toEqual([
                "5.2.1.dev",
                "5.2.1.rc1",
                "5.2.1",
                "5.9.0",
                "5.10.0",
                "6.0.0~rc1",
                "6.0.0",
                "2024.1.3",
            ]);
        });

        it("pushes nullish values to the end", () => {
            const input: (string | null | undefined)[] = ["5.2.1", null, "5.1.0", undefined, ""];
            const sorted = [...input].sort(compareVersions);
            expect(sorted.slice(0, 2)).toEqual(["5.1.0", "5.2.1"]);
            // null, undefined, "" are all "empty" and sort after real versions (order among them is unstable)
            expect(sorted.slice(2)).toHaveLength(3);
            expect(sorted.slice(2)).toEqual(expect.arrayContaining([null, undefined, ""]));
        });
    });
});
