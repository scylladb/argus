import { describe, it, expect } from "vitest";
import {
    GLOBAL_STATS_KEY,
    calculateWidgetStatsKey,
    calculateWidgetVersionKey,
    firstAvailableStats,
} from "./WidgetStatsKey";

const widget = (overrides = {}) => ({ position: 1, type: "testDashboard", filter: [], settings: {}, ...overrides });

describe("calculateWidgetStatsKey", () => {
    it("keeps the global bucket for a widget with no filter of any kind", () => {
        expect(calculateWidgetStatsKey(widget())).toBe(GLOBAL_STATS_KEY);
        expect(calculateWidgetStatsKey({ position: 3 })).toBe(GLOBAL_STATS_KEY);
    });

    it("keeps the existing key for an item-filtered widget", () => {
        const filtered = widget({ filter: ["abc"], position: 2 });

        expect(calculateWidgetStatsKey(filtered)).toBe(calculateWidgetVersionKey(filtered));
    });

    it("separates two widgets that differ only by their config parameter filters", () => {
        const narrowed = widget({
            position: 1,
            settings: { configParamFilters: [{ name: "sct_config.unified_package", value: null }] },
        });
        const plain = widget({ position: 2 });

        expect(calculateWidgetStatsKey(narrowed)).not.toBe(calculateWidgetStatsKey(plain));
        expect(calculateWidgetStatsKey(narrowed)).not.toBe(GLOBAL_STATS_KEY);
    });

    it("separates two narrowed widgets sharing one item filter", () => {
        const rows = [{ name: "sct_config.backend", value: "aws" }];
        const first = widget({ position: 1, filter: ["abc"], settings: { configParamFilters: rows } });
        const second = widget({ position: 2, filter: ["abc"], settings: { configParamFilters: rows } });

        expect(calculateWidgetStatsKey(first)).not.toBe(calculateWidgetStatsKey(second));
    });

    it("ignores a half-edited row with no name", () => {
        const blank = widget({ settings: { configParamFilters: [{ name: "", value: null }] } });

        expect(calculateWidgetStatsKey(blank)).toBe(GLOBAL_STATS_KEY);
    });
});

describe("calculateWidgetVersionKey", () => {
    it("ignores config parameter filters so the preselect still lands", () => {
        const narrowed = widget({ settings: { configParamFilters: [{ name: "cfg.a", value: "x" }] } });

        expect(calculateWidgetVersionKey(narrowed)).toBe(GLOBAL_STATS_KEY);
    });
});

describe("firstAvailableStats", () => {
    it("returns nothing when no bucket has stats", () => {
        expect(firstAvailableStats({})).toBeUndefined();
        expect(firstAvailableStats(undefined as never)).toBeUndefined();
        expect(firstAvailableStats({ a: undefined })).toBeUndefined();
    });

    it("returns the first bucket that has stats", () => {
        expect(firstAvailableStats({ a: undefined, b: { total: 3 }, c: { total: 9 } })).toEqual({ total: 3 });
    });
});
