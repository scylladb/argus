import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/svelte";

vi.mock("../../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));

import ResultTable from "./ResultTable.svelte";

const TEST_ID = "6f0c3a52-1b1d-4b7e-9a51-2a4f0c3d9e11";
const RESULT = {
    table_status: "PASS",
    description: "Throughput",
    columns: [{ name: "ops", unit: "op/s", type: "FLOAT" }],
    rows: ["write"],
    table_data: { write: { ops: { value: 100, status: "PASS" } } },
};

beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 404 }));
});

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});

describe("ResultTable metric history", () => {
    it("reads the metric history from the results router", async () => {
        render(ResultTable, { props: { table_name: "Throughput", result: RESULT, test_id: TEST_ID } });

        await fireEvent.click(screen.getByTitle("Show metric history"));

        await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringMatching(
            new RegExp(`^/api/v1/results/test\\?.*testId=${TEST_ID}`))));
    });
});
