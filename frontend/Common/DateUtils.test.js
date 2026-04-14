import { describe, it, expect } from "vitest";
import {
    timestampToISODate,
    generateWeeklyScheduleDate,
    generateWeeklyScheduleEndDate,
    permanentScheduleStart,
    permanentScheduleEnd,
    startDate,
    endDate,
} from "./DateUtils.js";

describe("timestampToISODate", () => {
    it("formats a timestamp without seconds by default", () => {
        // 2024-01-15T12:30:00Z in ms
        const ts = Date.UTC(2024, 0, 15, 12, 30, 0);
        expect(timestampToISODate(ts)).toBe("2024-01-15 12:30");
    });

    it("includes seconds when requested", () => {
        const ts = Date.UTC(2024, 0, 15, 12, 30, 45);
        expect(timestampToISODate(ts, true)).toBe("2024-01-15 12:30:45");
    });

    it("handles epoch zero", () => {
        expect(timestampToISODate(0)).toBe("1970-01-01 00:00");
    });
});

describe("generateWeeklyScheduleDate", () => {
    it("returns a Date object", () => {
        const result = generateWeeklyScheduleDate(new Date("2024-03-20T12:00:00Z"));
        expect(result).toBeInstanceOf(Date);
    });

    it("returns a Friday (day 5)", () => {
        // Wednesday 2024-03-20 -> should find the previous Friday 2024-03-15
        const result = generateWeeklyScheduleDate(new Date("2024-03-20T12:00:00Z"));
        expect(result.getUTCDay()).toBe(5);
    });

    it("returns a date in the past relative to the input", () => {
        const today = new Date("2024-03-20T12:00:00Z");
        const result = generateWeeklyScheduleDate(today);
        expect(result.getTime()).toBeLessThanOrEqual(today.getTime());
    });
});

describe("generateWeeklyScheduleEndDate", () => {
    it("returns a Thursday (day 4)", () => {
        const start = new Date("2024-03-15T00:00:00Z"); // Friday
        const result = generateWeeklyScheduleEndDate(start);
        expect(result.getUTCDay()).toBe(4);
    });

    it("returns a date after the start date", () => {
        const start = new Date("2024-03-15T00:00:00Z");
        const result = generateWeeklyScheduleEndDate(start);
        expect(result.getTime()).toBeGreaterThan(start.getTime());
    });
});

describe("permanentScheduleStart", () => {
    it("returns a date 1 year before the input", () => {
        const today = new Date("2024-06-15T00:00:00Z");
        const result = permanentScheduleStart(today);
        expect(result.getUTCFullYear()).toBe(2023);
        expect(result.getUTCMonth()).toBe(5); // June = 5
    });

    it("returns a Date object", () => {
        expect(permanentScheduleStart()).toBeInstanceOf(Date);
    });
});

describe("permanentScheduleEnd", () => {
    it("returns a date 2 years after the input", () => {
        const today = new Date("2024-06-15T00:00:00Z");
        const result = permanentScheduleEnd(today);
        expect(result.getUTCFullYear()).toBe(2026);
        expect(result.getUTCMonth()).toBe(5); // June = 5
    });
});

describe("startDate", () => {
    it("uses weekly schedule for perpetual releases", () => {
        const release = { perpetual: true };
        const today = new Date("2024-03-20T12:00:00Z");
        const result = startDate(release, today);
        // Should return a Friday (from generateWeeklyScheduleDate)
        expect(result.getUTCDay()).toBe(5);
    });

    it("uses permanent schedule for non-perpetual releases", () => {
        const release = { perpetual: false };
        const today = new Date("2024-06-15T00:00:00Z");
        const result = startDate(release, today);
        // Should return 1 year before (from permanentScheduleStart)
        expect(result.getUTCFullYear()).toBe(2023);
    });

    it("uses permanent schedule for null/undefined release", () => {
        const today = new Date("2024-06-15T00:00:00Z");
        const result = startDate(null, today);
        expect(result.getUTCFullYear()).toBe(2023);
    });
});

describe("endDate", () => {
    it("uses weekly schedule end for perpetual releases", () => {
        const release = { perpetual: true };
        const start = new Date("2024-03-15T00:00:00Z"); // Friday
        const result = endDate(release, start);
        // Should return a Thursday (from generateWeeklyScheduleEndDate)
        expect(result.getUTCDay()).toBe(4);
    });

    it("uses permanent schedule end for non-perpetual releases", () => {
        const release = { perpetual: false };
        const start = new Date("2024-06-15T00:00:00Z");
        const result = endDate(release, start);
        expect(result.getUTCFullYear()).toBe(2026);
    });
});
