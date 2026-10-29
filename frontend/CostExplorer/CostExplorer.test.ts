import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/svelte";

vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../Common/ApiUtils", () => ({ fetchJson: vi.fn() }));
vi.hoisted(() => {
    window.matchMedia = (query: string) =>
        ({ matches: false, media: query, onchange: null, addEventListener: () => {}, removeEventListener: () => {},
           addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }) as unknown as MediaQueryList;
    Element.prototype.getAnimations = () => [];
});
vi.mock("chart.js/auto", () => ({
    default: class {
        config = { data: {}, options: {} };
        update() {}
        destroy() {}
    },
}));

import { fetchJson } from "../Common/ApiUtils";
import { sendMessage } from "../Stores/AlertStore";
import CostExplorer from "./CostExplorer.svelte";

const RESPONSE = {
    window: { from: "2026-10-01T00:00:00Z", to: "2026-11-01T00:00:00Z", granularity: "day", breakdown: "group", tiers: [] },
    span: null,
    tiles: { spend: 118406.2, previous_spend: 100000, weekly_run_rate: 9208.3, errored_spend: 21733, leaked_spend: 0,
             leaked_count: 0, runs: 10, priced_runs: 9 },
    series: { buckets: ["2026-10-01", "2026-10-02"], backends: { aws: [1, 2], gce: [0, 3] } },
    releases: [],
    top_runs: [],
    coverage: { complete: 9, partial: 0, none: 1 },
    tiers: { spot: { spend: 0, items: 0 }, on_demand: { spend: 0, items: 0 }, untiered: { spend: 0, items: 0 } },
    spot_terminations: { count: 0, spot_runs: 0, rate: 0, spend: 0, by_location: [] }
};

const fetchMock = vi.mocked(fetchJson);

beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(async (url: string) => {
        if (url.startsWith("/api/v1/cost/explorer")) return RESPONSE;
        return [];
    });
});

afterEach(cleanup);

describe("CostExplorer.svelte", () => {
    it("requests the panels with the filters of the query string", async () => {
        render(CostExplorer, { props: { initialSearch: "?releaseName=2026.1&releaseName=2026.2&tier=spot&status=failed&granularity=day&from=2026-10-01&to=2026-10-31" } });

        await waitFor(() => expect(screen.getByText("$118,406")).toBeTruthy());
        const url = fetchMock.mock.calls.map(([called]) => called).find((called) => called.startsWith("/api/v1/cost/explorer"));
        const params = new URLSearchParams(url!.split("?")[1]);
        expect(params.getAll("releaseName")).toEqual(["2026.1", "2026.2"]);
        expect(params.getAll("tier")).toEqual(["spot"]);
        expect(params.getAll("status")).toEqual(["failed"]);
        expect(params.get("granularity")).toBe("day");
        expect(params.get("from")).toBe("2026-10-01T00:00:00Z");
        expect(params.get("to")).toBe("2026-11-01T00:00:00Z");
        expect(screen.getByText("Spend over time, by backend")).toBeTruthy();
    });

    it("moves the window onto a release whose runs lie outside it", async () => {
        fetchMock.mockImplementation(async (url: string) => {
            if (!url.startsWith("/api/v1/cost/explorer")) return [];
            const params = new URLSearchParams(url.split("?")[1]);
            const inside = params.get("from")! <= "2025-06-20T00:00:00Z";
            return { ...RESPONSE, tiles: { ...RESPONSE.tiles, runs: inside ? 4 : 0 },
                     span: { from: "2025-01-10T08:00:00Z", to: "2025-06-20T18:30:00Z" } };
        });

        render(CostExplorer, { props: { initialSearch: "?releaseName=2025.1&from=2026-10-01&to=2026-10-31" } });

        await waitFor(() => expect(fetchMock.mock.calls.filter(([u]) => u.startsWith("/api/v1/cost/explorer"))).toHaveLength(2));
        const second = new URLSearchParams(fetchMock.mock.calls.filter(([u]) => u.startsWith("/api/v1/cost/explorer"))[1][0].split("?")[1]);
        expect(second.get("from")).toBe("2025-03-22T00:00:00Z");
        expect(second.get("to")).toBe("2025-06-21T00:00:00Z");
        expect(screen.getByRole("button", { name: "Fit to releases" })).toBeTruthy();
    });

    it("reports a failed load", async () => {
        fetchMock.mockImplementation(async (url: string) => {
            if (url.startsWith("/api/v1/cost/explorer")) throw new Error("The window must end after it starts");
            return [];
        });

        render(CostExplorer, { props: { initialSearch: "" } });

        await waitFor(() => expect(screen.getByText("The window must end after it starts")).toBeTruthy());
        expect(sendMessage).toHaveBeenCalledWith("error", "The window must end after it starts", "CostExplorer::load");
    });
});
