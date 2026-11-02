import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/svelte";

vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("./ResultsGraph.svelte", () => ({ default: () => {} }));

import ResultsGraphs from "./ResultsGraphs.svelte";

const TEST_ID = "6f0c3a52-1b1d-4b7e-9a51-2a4f0c3d9e11";
const GRAPH = { options: { plugins: { title: { text: "Throughput - ops" } } }, data: { datasets: [] } };
const VIEW = { test_id: TEST_ID, id: "view-1", name: "Saved View", description: "", graphs: {} };

function respond(response: unknown) {
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ status: "ok", response }) });
}

beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((url: string) => {
        if (url.startsWith("/api/v1/results/test?")) {
            return respond({ graphs: [GRAPH], ticks: {}, graph_views: [VIEW], releases_filters: [] });
        }
        return respond(VIEW);
    }));
});

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});

describe("ResultsGraphs routes", () => {
    it("reads the graphs from the results router", async () => {
        render(ResultsGraphs, { props: { test_id: TEST_ID } });

        await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringMatching(
            new RegExp(`^/api/v1/results/test\\?.*testId=${TEST_ID}`))));
    });

    it("creates a graph view through the results router", async () => {
        render(ResultsGraphs, { props: { test_id: TEST_ID } });

        await fireEvent.click(screen.getByText("+ View"));
        await fireEvent.input(screen.getByLabelText("Name"), { target: { value: "New View" } });
        await fireEvent.click(screen.getByText("Save"));

        expect(fetch).toHaveBeenCalledWith("/api/v1/results/graph-view/create", expect.objectContaining({
            method: "POST",
            body: JSON.stringify({ testId: TEST_ID, name: "New View", description: "" }),
        }));
    });

    it("updates a graph view through the results router", async () => {
        render(ResultsGraphs, { props: { test_id: TEST_ID } });

        await fireEvent.click(await screen.findByTitle("add to graph view"));
        await fireEvent.change(screen.getByRole("combobox"), { target: { value: VIEW.name } });
        await fireEvent.click(screen.getByText("Add"));

        expect(fetch).toHaveBeenCalledWith("/api/v1/results/graph-view/update", expect.objectContaining({
            method: "POST",
        }));
    });
});
