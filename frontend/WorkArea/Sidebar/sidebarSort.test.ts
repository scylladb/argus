import { describe, it, expect } from "vitest";
import { displayName, duplicateNames, pinnedFirst, sortTests } from "./sidebarSort";

const test = (id: string, name: string, pretty_name: string | null = null) => ({ id, name, pretty_name });
const summary = (status: string) => ({ status, investigation_status: "not_investigated", start_time: null });

describe("sortTests", () => {
    it("orders by status severity, then by name", () => {
        const tests = [test("a", "zeta"), test("b", "alpha"), test("c", "beta"), test("d", "gamma")];
        const sorted = sortTests(tests, {
            a: summary("passed"),
            b: summary("not_run"),
            c: summary("failed"),
            d: summary("passed"),
        });

        expect(sorted.map((t) => t.id)).toEqual(["c", "d", "a", "b"]);
    });

    it("orders by name when no stats are known", () => {
        const tests = [test("a", "test-10"), test("b", "test-9"), test("c", "Alpha", null)];

        expect(sortTests(tests).map((t) => t.id)).toEqual(["c", "b", "a"]);
    });

    it("re-sorts when the stats change and leaves the input untouched", () => {
        const tests = [test("a", "alpha"), test("b", "beta")];

        const before = sortTests(tests, { a: summary("passed"), b: summary("passed") });
        const after = sortTests(tests, { a: summary("passed"), b: summary("failed") });

        expect(before.map((t) => t.id)).toEqual(["a", "b"]);
        expect(after.map((t) => t.id)).toEqual(["b", "a"]);
        expect(tests.map((t) => t.id)).toEqual(["a", "b"]);
    });
});

describe("pinnedFirst", () => {
    it("lifts the pinned items and keeps the order within each part", () => {
        const items = [test("a", "a"), test("b", "b"), test("c", "c"), test("d", "d")];

        expect(pinnedFirst(items, new Set(["d", "b"])).map((t) => t.id)).toEqual(["b", "d", "a", "c"]);
    });
});

describe("duplicateNames", () => {
    it("returns the display names that more than one item shares", () => {
        const items = [
            test("a", "core-qa", "Cluster - Core QA Longevities"),
            test("b", "core-qa-2", "Cluster - Core QA Longevities"),
            test("c", "tier1", "Cluster - Tier1 Longevities"),
        ];

        expect([...duplicateNames(items)]).toEqual(["Cluster - Core QA Longevities"]);
    });
});

describe("displayName", () => {
    it("prefers the pretty name", () => {
        expect(displayName(test("a", "raw", "Pretty"))).toBe("Pretty");
        expect(displayName(test("a", "raw"))).toBe("raw");
    });
});
