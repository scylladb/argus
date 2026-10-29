import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/svelte";

vi.mock("../../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../../Common/ApiUtils", () => ({ fetchJson: vi.fn() }));
vi.mock("chart.js/auto", () => ({
    default: class {
        config = { data: {}, options: {} };
        update() {}
        destroy() {}
    },
}));

import { fetchJson } from "../../Common/ApiUtils";
import ViewCosts from "./ViewCosts.svelte";

const RESPONSE = {
    window: { from: "2026-10-15T00:00:00Z", to: "2026-10-29T00:00:00Z", granularity: "day", breakdown: "group", tiers: [] },
    span: null,
    tiles: { spend: 4321, previous_spend: 4000, weekly_run_rate: 2160.5, errored_spend: 100, leaked_spend: 0, leaked_count: 0,
             runs: 12, priced_runs: 12 },
    series: { buckets: ["2026-10-15"], backends: { aws: [4321] } },
    releases: [], top_runs: [], coverage: { complete: 12, partial: 0, none: 0, estimate_only: { count: 0, spend: 0 } },
    tiers: { spot: { spend: 0, items: 0 }, on_demand: { spend: 0, items: 0 }, untiered: { spend: 0, items: 0 } },
    spot_terminations: { count: 0, spot_runs: 0, rate: 0, spend: 0, by_location: [] }
};

const fetchMock = vi.mocked(fetchJson);

beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(RESPONSE);
});

afterEach(cleanup);

describe("ViewCosts.svelte", () => {
    it("reads the view's costs for the configured days and links the page", async () => {
        render(ViewCosts, { props: { dashboardObject: { id: "v-1" }, settings: { days: 14 } } });

        await waitFor(() => expect(screen.getByText("$4,321")).toBeTruthy());
        expect(fetchMock).toHaveBeenCalledWith("/api/v1/views/widgets/costs?view_id=v-1&days=14");
        const link = screen.getByRole("link", { name: "Open in the Cost Explorer" });
        const params = new URLSearchParams(link.getAttribute("href")!.split("?")[1]);
        expect(params.get("viewId")).toBe("v-1");
        expect(params.get("from")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });

    it("defaults to 30 days", async () => {
        render(ViewCosts, { props: { dashboardObject: { id: "v-2" }, settings: {} } });

        await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/views/widgets/costs?view_id=v-2&days=30"));
    });
});
