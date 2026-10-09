import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, fireEvent, within } from "@testing-library/svelte";

vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));

import TestRunsSelector from "./TestRunsSelector.svelte";

const TEST_INFO = {
    test: { id: "6f0c3a52-1b1d-4b7e-9a51-2a4f0c3d9e11", name: "longevity-frobnicator-4h" },
    release: { name: "master" },
    group: { name: "longevity" },
};

const RUNS = [{ id: "a7b1c2d3-0000-4000-8000-000000000412", status: "failed", build_number: 412 }];

class FakeIntersectionObserver {
    observe() {}
    disconnect() {}
}

beforeEach(() => {
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 404 }));
});

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});

describe("TestRunsSelector ignore-runs dialog", () => {
    it("opens the dialog of the selector that was clicked", async () => {
        const props = { testInfo: TEST_INFO, testId: TEST_INFO.test.id, runs: RUNS, clickedTestRuns: {} };
        const first = render(TestRunsSelector, { props });
        const second = render(TestRunsSelector, { props });

        await fireEvent.click(within(second.container).getByTitle("Ignore failed runs"));

        expect(second.container.querySelector(".modal")?.classList.contains("show")).toBe(true);
        expect(first.container.querySelector(".modal")?.classList.contains("show")).toBe(false);
    });
});
