import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/svelte";

vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));

import TestRunsSelector from "./TestRunsSelector.svelte";

const TEST_INFO = {
    test: { id: "6f0c3a52-1b1d-4b7e-9a51-2a4f0c3d9e11", name: "longevity-frobnicator-4h" },
    release: { name: "master" },
    group: { name: "longevity" },
};

const RUNS = [{ id: "a7b1c2d3-0000-4000-8000-000000000412", status: "failed", build_number: 412 }];
const EDITABLE_INFO = { ...TEST_INFO, release: { name: "staging", user_editable: true } };
const DELETE_RUN = { name: "Delete run #412" };

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

describe("TestRunsSelector run deletion", () => {
    it("shows the delete button only on an open run of a user-editable release", () => {
        const open = { [RUNS[0].id]: true };

        render(TestRunsSelector, { props: { testInfo: TEST_INFO, testId: TEST_INFO.test.id, runs: RUNS, clickedTestRuns: open } });
        expect(screen.queryByRole("button", DELETE_RUN)).toBeNull();
        cleanup();

        render(TestRunsSelector, { props: { testInfo: EDITABLE_INFO, testId: TEST_INFO.test.id, runs: RUNS, clickedTestRuns: {} } });
        expect(screen.queryByRole("button", DELETE_RUN)).toBeNull();
        cleanup();

        render(TestRunsSelector, { props: { testInfo: EDITABLE_INFO, testId: TEST_INFO.test.id, runs: RUNS, clickedTestRuns: open } });
        expect(screen.getByRole("button", DELETE_RUN)).toBeTruthy();
    });

    it("deletes the run after a plain confirmation and dispatches runDeleted", async () => {
        const fetchMock = vi.fn((url: string, init?: RequestInit) =>
            init?.method === "DELETE"
                ? Promise.resolve({ json: () => Promise.resolve({ status: "ok", response: { deleted: RUNS[0].id } }) })
                : Promise.resolve({ status: 404 }));
        vi.stubGlobal("fetch", fetchMock);
        const onRunDeleted = vi.fn();
        render(TestRunsSelector, {
            props: { testInfo: EDITABLE_INFO, testId: TEST_INFO.test.id, runs: RUNS, clickedTestRuns: { [RUNS[0].id]: true } },
            events: { runDeleted: onRunDeleted },
        });

        await fireEvent.click(screen.getByRole("button", DELETE_RUN));
        expect(screen.queryByLabelText(/to confirm/)).toBeNull();
        await fireEvent.click(screen.getByRole("button", { name: "Delete" }));

        await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`/api/v1/test/${TEST_INFO.test.id}/run/${RUNS[0].id}`, { method: "DELETE" }));
        await waitFor(() => expect(onRunDeleted).toHaveBeenCalledTimes(1));
        expect(onRunDeleted.mock.calls[0][0].detail).toEqual({ id: RUNS[0].id });
        expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    });
});
