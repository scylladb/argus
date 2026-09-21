import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/svelte";

vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));

import CostsTab from "./CostsTab.svelte";

const EMPTY_COST = {
    estimated_cost: null,
    actual_cost: null,
    items: [],
    by_category: {},
};

const FULL_COST = {
    estimated_cost: 118.4,
    actual_cost: 20,
    items: [
        { name: "longevity-db-node-1", category: "db_node", cost: 12.3, pricing_tier: "spot", leaked: false },
        { name: "longevity-db-node-2", category: "db_node", cost: 4, pricing_tier: null, leaked: false },
        { name: "orphan-loader", category: "loader", cost: 3.7, pricing_tier: null, leaked: true },
    ],
    by_category: { db_node: 16.3, loader: 3.7 },
};

function stubCost(response: unknown) {
    const fetchSpy = vi.fn().mockResolvedValue({
        json: () => Promise.resolve({ status: "ok", response }),
    });
    vi.stubGlobal("fetch", fetchSpy);
    return fetchSpy;
}

afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
});

describe("CostsTab.svelte", () => {
    it("reads the cost of the run it was given", async () => {
        const fetchSpy = stubCost(EMPTY_COST);

        render(CostsTab, { props: { runId: "run-1" } });

        await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
        expect(fetchSpy.mock.calls[0][0]).toBe("/api/v1/cost/run/run-1");
    });

    it("states that nothing was reported when the run has no cost", async () => {
        stubCost(EMPTY_COST);

        render(CostsTab, { props: { runId: "run-1" } });

        await waitFor(() => expect(screen.getByText("No cost reported for this run.")).toBeTruthy());
    });

    it("shows both totals when the run has a cost", async () => {
        stubCost(FULL_COST);

        render(CostsTab, { props: { runId: "run-1" } });

        await waitFor(() => expect(screen.getByText("$118.40")).toBeTruthy());
        expect(screen.getByText("$20.00")).toBeTruthy();
    });

    it("never renders an unknown total as zero", async () => {
        stubCost({ ...FULL_COST, actual_cost: null });

        render(CostsTab, { props: { runId: "run-1" } });

        await waitFor(() => expect(screen.getByText("Not reported")).toBeTruthy());
        expect(screen.queryByText("$0.00")).toBeNull();
    });

    it("lists the items under their category with a subtotal", async () => {
        stubCost(FULL_COST);

        render(CostsTab, { props: { runId: "run-1" } });

        await waitFor(() => expect(screen.getByText("longevity-db-node-1")).toBeTruthy());
        expect(screen.getByText("db_node")).toBeTruthy();
        expect(screen.getByText("$16.30")).toBeTruthy();
        expect(screen.getByText("$12.30")).toBeTruthy();
        expect(screen.getByText("spot")).toBeTruthy();
    });

    it("marks an item that leaked", async () => {
        stubCost(FULL_COST);

        render(CostsTab, { props: { runId: "run-1" } });

        await waitFor(() => expect(screen.getByText("Leaked")).toBeTruthy());
    });
});
