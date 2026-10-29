import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/svelte";
import StatTiles from "./StatTiles.svelte";

const TILES = {
    spend: 118406.2,
    previous_spend: 105340,
    weekly_run_rate: 9208.3,
    errored_spend: 21733,
    leaked_spend: 4918,
    leaked_count: 31,
    runs: 1284,
    priced_runs: 1182,
};

afterEach(cleanup);

describe("StatTiles.svelte", () => {
    it("shows the spend with its trend and its coverage", () => {
        render(StatTiles, { props: { tiles: TILES, windowDays: 90 } });

        expect(screen.getByText("$118,406")).toBeTruthy();
        expect(screen.getByText("▲ 12.4% vs the previous 90 days")).toBeTruthy();
        expect(screen.getByText("Known for 1,182 of 1,284 runs (92.1%)")).toBeTruthy();
        expect(screen.getByText("18.4% of total spend")).toBeTruthy();
        expect(screen.getByText("31 resources reaped late")).toBeTruthy();
    });

    it("says no data instead of zero when no run has a figure", () => {
        render(StatTiles, { props: { tiles: { ...TILES, spend: 0, priced_runs: 0, runs: 3 }, windowDays: 30 } });

        expect(screen.getAllByText("No data")).toHaveLength(4);
        expect(screen.getByText("Known for 0 of 3 runs (0.0%)")).toBeTruthy();
    });
});
