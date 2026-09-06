import { describe, it, expect } from "vitest";
import { formatCost, formatRate, isLiveCost, resourceCost, runCostSummary } from "./CostUtils";

const HOUR = 3600;
const NOW = 1_700_000_000;

const terminated = (cost: number | null, extra = {}) => ({
    state: "terminated",
    instance_info: {
        creation_time: NOW - 2 * HOUR,
        termination_time: NOW - HOUR,
        cost,
        ...extra,
    },
});

const running = (price_per_hour: number | null, ageHours = 2, extra = {}) => ({
    state: "running",
    instance_info: {
        creation_time: NOW - ageHours * HOUR,
        termination_time: 0,
        price_per_hour,
        ...extra,
    },
});

describe("resourceCost", () => {
    it("uses the cost SCT reported at termination", () => {
        expect(resourceCost(terminated(12.5), NOW)).toBe(12.5);
    });

    it("returns null for a terminated resource with no cost", () => {
        expect(resourceCost(terminated(null), NOW)).toBeNull();
    });

    it("does not back-fill a terminated resource from its hourly rate", () => {
        expect(resourceCost(terminated(null, { price_per_hour: 1.0 }), NOW)).toBeNull();
    });

    it("extrapolates a running resource from its hourly rate", () => {
        expect(resourceCost(running(1.5, 2), NOW)).toBeCloseTo(3.0, 6);
    });

    it("treats a zero rate as unknown rather than free", () => {
        expect(resourceCost(running(0), NOW)).toBeNull();
    });

    it("treats a zero cost as unknown rather than free", () => {
        expect(resourceCost(terminated(0), NOW)).toBeNull();
    });

    it("returns null when there is no rate and no cost", () => {
        expect(resourceCost(running(null), NOW)).toBeNull();
    });

    it("prefers a reported cost over the rate even while running", () => {
        expect(resourceCost(running(1.5, 2, { cost: 9.99 }), NOW)).toBe(9.99);
    });

    it("clamps a creation time in the future to zero", () => {
        expect(resourceCost(running(1.5, -1), NOW)).toBe(0);
    });

    it("survives a resource with no instance_info", () => {
        expect(resourceCost({ state: "running" }, NOW)).toBeNull();
    });
});

describe("isLiveCost", () => {
    it("is true for a running resource priced by rate only", () => {
        expect(isLiveCost(running(1.5))).toBe(true);
    });

    it("is false once a final cost is reported", () => {
        expect(isLiveCost(running(1.5, 2, { cost: 3.0 }))).toBe(false);
    });

    it("is false for a terminated resource", () => {
        expect(isLiveCost(terminated(12.5))).toBe(false);
    });

    it("is false without a rate", () => {
        expect(isLiveCost(running(null))).toBe(false);
    });
});

describe("runCostSummary", () => {
    it("sums known costs and flags nothing when all are known", () => {
        const summary = runCostSummary([terminated(1.5), terminated(2.5)], NOW);
        expect(summary.total).toBeCloseTo(4.0, 6);
        expect(summary.partial).toBe(false);
        expect(summary.known).toBe(2);
        expect(summary.unknown).toBe(0);
    });

    it("marks the total partial when a terminated resource has no cost", () => {
        const summary = runCostSummary([terminated(1.5), terminated(null)], NOW);
        expect(summary.total).toBeCloseTo(1.5, 6);
        expect(summary.partial).toBe(true);
        expect(summary.unknown).toBe(1);
    });

    it("mixes live and final costs", () => {
        const summary = runCostSummary([terminated(1.0), running(2.0, 1.5)], NOW);
        expect(summary.total).toBeCloseTo(4.0, 6);
        expect(summary.partial).toBe(false);
    });

    it("reports no false zero for a run with no cost data", () => {
        const summary = runCostSummary([terminated(null), running(null)], NOW);
        expect(summary.known).toBe(0);
        expect(summary.total).toBe(0);
        expect(summary.partial).toBe(true);
    });

    it("handles a missing resource list", () => {
        expect(runCostSummary(undefined, NOW)).toEqual({ total: 0, partial: false, known: 0, unknown: 0 });
    });
});

describe("formatting", () => {
    it("formats a cost to cents", () => {
        expect(formatCost(12.3456)).toBe("$12.35");
    });

    it("renders a placeholder for an unknown cost", () => {
        expect(formatCost(null)).toBe("N/A");
        expect(formatCost(undefined, "—")).toBe("—");
    });

    it("formats an hourly rate", () => {
        expect(formatRate(1.2345)).toBe("$1.234/h");
    });

    it("renders a placeholder for an unknown rate", () => {
        expect(formatRate(null)).toBe("N/A");
        expect(formatRate(0)).toBe("N/A");
    });
});
