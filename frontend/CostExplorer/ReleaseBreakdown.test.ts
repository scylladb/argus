import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import ReleaseBreakdown from "./ReleaseBreakdown.svelte";

const rows = (count: number) =>
    Array.from({ length: count }, (_, index) => ({
        id: `row-${index}`,
        name: `group-${index}`,
        runs: 2,
        priced_runs: 2,
        spend: 100 - index,
        cost_per_run: (100 - index) / 2,
    }));

afterEach(cleanup);

describe("ReleaseBreakdown.svelte", () => {
    it("shows each release with its rows and the cost per run", () => {
        render(ReleaseBreakdown, {
            props: {
                breakdown: "group",
                releases: [
                    { id: "rel-1", name: "2026.1", runs: 3, priced_runs: 2, spend: 30, rows: [
                        { id: "g-1", name: "longevity", runs: 3, priced_runs: 2, spend: 30, cost_per_run: 15 },
                    ] },
                    { id: "00000000-0000-0000-0000-000000000000", name: "Unassigned", runs: 1, priced_runs: 0, spend: 0, rows: [
                        { id: null, name: "Unassigned", runs: 1, priced_runs: 0, spend: 0, cost_per_run: null },
                    ] },
                ],
            },
        });

        expect(screen.getByText("2026.1")).toBeTruthy();
        expect(screen.getByText("longevity")).toBeTruthy();
        expect(screen.getAllByRole("columnheader", { name: /Group/ })).toHaveLength(1);
        expect(screen.getByText("$15.00")).toBeTruthy();
        expect(screen.getAllByText("Unassigned")).toHaveLength(2);
        expect(screen.getByText("No data")).toBeTruthy();
        expect(screen.getByText("100.0%")).toBeTruthy();
    });

    it("sorts the rows by a clicked column", async () => {
        render(ReleaseBreakdown, {
            props: { breakdown: "group", releases: [{ id: "rel-1", name: "2026.1", runs: 6, priced_runs: 6, spend: 60, rows: [
                { id: "a", name: "alpha", runs: 1, priced_runs: 1, spend: 30, cost_per_run: 30 },
                { id: "b", name: "beta", runs: 3, priced_runs: 3, spend: 20, cost_per_run: 6.67 },
                { id: "c", name: "gamma", runs: 2, priced_runs: 2, spend: 10, cost_per_run: 5 },
            ] }] },
        });
        const names = () => screen.getAllByRole("row").slice(2).map((row) => row.querySelector("td")?.textContent?.trim());

        expect(names()).toEqual(["alpha", "beta", "gamma"]);
        await fireEvent.click(screen.getByRole("button", { name: /^Runs/ }));
        expect(names()).toEqual(["beta", "gamma", "alpha"]);
        await fireEvent.click(screen.getByRole("button", { name: /^Runs/ }));
        expect(names()).toEqual(["alpha", "gamma", "beta"]);
        await fireEvent.click(screen.getByRole("button", { name: /^Group/ }));
        expect(names()).toEqual(["alpha", "beta", "gamma"]);
    });

    it("folds long lists behind a toggle", async () => {
        render(ReleaseBreakdown, {
            props: { breakdown: "test", releases: [{ id: "rel-1", name: "2026.1", runs: 24, priced_runs: 24, spend: 1000, rows: rows(12) }] },
        });

        expect(screen.queryByText("group-11")).toBeNull();
        await fireEvent.click(screen.getByText("Show all 12"));
        expect(screen.getByText("group-11")).toBeTruthy();
        expect(screen.getByText("Show fewer")).toBeTruthy();
    });
});
