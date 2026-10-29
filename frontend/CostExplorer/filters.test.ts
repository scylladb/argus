import { describe, expect, it } from "vitest";
import { apiParams, defaultFilters, fitRange, overlaps, parseFilters, presetRange, serializeFilters } from "./filters";

const NOW = new Date("2026-10-29T12:00:00Z");

describe("filters", () => {
    it("defaults to the last 90 days with group and week and no filter", () => {
        const filters = defaultFilters(NOW);
        expect(filters.from).toBe("2026-07-31");
        expect(filters.to).toBe("2026-10-29");
        expect(filters.breakdown).toBe("group");
        expect(filters.granularity).toBe("week");
        expect(filters.releaseNames).toEqual([]);
        expect(filters.statuses).toEqual([]);
        expect(filters.tiers).toEqual([]);
        expect(presetRange(7, NOW)).toEqual({ from: "2026-10-22", to: "2026-10-29" });
    });

    it("round-trips several values per filter through the query string", () => {
        const filters = {
            ...defaultFilters(NOW),
            releaseNames: ["2026.1", "2026.2"],
            groupIds: ["g-1"],
            statuses: ["failed", "test_error"],
            tiers: ["spot" as const],
            breakdown: "test" as const,
            granularity: "day" as const,
        };
        const query = serializeFilters(filters);
        expect(query).not.toContain("testId");
        expect(query).toContain("releaseName=2026.1&releaseName=2026.2");
        expect(parseFilters(`?${query}`, NOW)).toEqual(filters);
    });

    it("falls back to the defaults on a bad value and drops repeats", () => {
        const filters = parseFilters("?from=yesterday&tier=free&tier=spot&tier=spot&granularity=hour&breakdown=release", NOW);
        expect(filters.from).toBe("2026-07-31");
        expect(filters.tiers).toEqual(["spot"]);
        expect(filters.granularity).toBe("week");
        expect(filters.breakdown).toBe("group");
    });

    it("sends the window as UTC datetimes with an inclusive end date", () => {
        const params = apiParams({ ...defaultFilters(NOW), from: "2026-10-01", to: "2026-10-31", viewId: "v-1",
                                   tiers: ["spot", "on-demand"] });
        expect(params.get("from")).toBe("2026-10-01T00:00:00Z");
        expect(params.get("to")).toBe("2026-11-01T00:00:00Z");
        expect(params.get("viewId")).toBe("v-1");
        expect(params.get("granularity")).toBe("week");
        expect(params.has("releaseName")).toBe(false);
        expect(params.getAll("tier")).toEqual(["spot", "on-demand"]);
    });

    it("fits the window onto the last 90 days of a release span", () => {
        const span = { from: "2025-01-10T08:00:00Z", to: "2025-06-20T18:30:00Z" };
        expect(fitRange(span)).toEqual({ from: "2025-03-22", to: "2025-06-20" });
        expect(fitRange({ from: "2025-06-01T00:00:00Z", to: "2025-06-20T18:30:00Z" })).toEqual({ from: "2025-06-01", to: "2025-06-20" });
        expect(overlaps({ ...defaultFilters(NOW), from: "2025-05-01", to: "2025-07-01" }, span)).toBe(true);
        expect(overlaps({ ...defaultFilters(NOW), from: "2026-07-31", to: "2026-10-29" }, span)).toBe(false);
    });
});
