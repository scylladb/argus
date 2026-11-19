import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import NumberStats from "./NumberStats.svelte";

afterEach(cleanup);

const STATS = {
    total: 10,
    passed: 5,
    failed: 5,
    lastStatus: "failed",
    investigated: { failed: 2 },
    not_investigated: { failed: 3, passed: 5 },
};

const transition = () => new Promise((resolve) => setTimeout(resolve, 50));

describe("NumberStats investigation bar", () => {
    it("starts collapsed", () => {
        render(NumberStats, { stats: STATS, displayInvestigations: true });

        expect(screen.getByRole("button", { expanded: false })).toBeTruthy();
    });

    it("expands and moves the focus to the first quick select", async () => {
        render(NumberStats, { stats: STATS, displayInvestigations: true });
        const bar = screen.getByRole("button", { expanded: false });
        bar.focus();

        await fireEvent.click(bar);

        expect(bar.getAttribute("aria-expanded")).toBe("true");
        expect(document.activeElement).toBe(screen.getAllByRole("button", { name: "Failed" })[0]);
    });

    it("collapses from Hide and returns the focus to the bar", async () => {
        render(NumberStats, { stats: STATS, displayInvestigations: true });
        const bar = screen.getByRole("button", { expanded: false });
        await fireEvent.click(bar);
        await transition();

        await fireEvent.click(screen.getByRole("button", { name: "Hide" }));

        expect(bar.getAttribute("aria-expanded")).toBe("false");
        expect(document.activeElement).toBe(bar);
    });

    it("moves the focus to Hide when no status has a count", async () => {
        render(NumberStats, { stats: { total: 0 }, displayInvestigations: true });
        const bar = screen.getByRole("button", { expanded: false });

        await fireEvent.click(bar);

        expect(bar.getAttribute("aria-expanded")).toBe("true");
        expect(document.activeElement).toBe(screen.getByRole("button", { name: "Hide" }));
    });
});
