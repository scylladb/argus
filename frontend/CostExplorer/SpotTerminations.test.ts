import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/svelte";
import SpotTerminations from "./SpotTerminations.svelte";

afterEach(cleanup);

describe("SpotTerminations.svelte", () => {
    it("shows the count, the rate as a percentage and the locations", () => {
        render(SpotTerminations, {
            props: {
                terminations: {
                    count: 14, spot_runs: 420, rate: 0.0333, spend: 1900,
                    by_location: [{ backend: "aws", region: "eu-west-1", count: 9, spend: 1200 }],
                },
            },
        });

        expect(screen.getByText("14")).toBeTruthy();
        expect(screen.getByText("3.3%")).toBeTruthy();
        expect(screen.getByText("$1,900")).toBeTruthy();
        expect(screen.getByText("eu-west-1")).toBeTruthy();
    });

    it("distinguishes no spot runs from no reclaim", () => {
        const { unmount } = render(SpotTerminations, {
            props: { terminations: { count: 0, spot_runs: 0, rate: 0, spend: 0, by_location: [] } },
        });
        expect(screen.getByText("No spot run in this range.")).toBeTruthy();
        unmount();

        render(SpotTerminations, {
            props: { terminations: { count: 0, spot_runs: 7, rate: 0, spend: 0, by_location: [] } },
        });
        expect(screen.getByText("None of the 7 spot runs was reclaimed.")).toBeTruthy();
    });
});
