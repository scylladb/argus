import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/svelte";

vi.mock("../argus", () => ({ applicationCurrentUser: { roles: [] } }));
vi.mock("../Common/PluginDispatch", () => ({ AVAILABLE_PLUGINS: {}, isPluginSupported: () => true }));
vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("./TestRunDispatcher.svelte", () => ({ default: vi.fn() }));

import TestRunDispatcher from "./TestRunDispatcher.svelte";
import TestRuns from "./TestRuns.svelte";

const TEST_ID = "6f0c3a52-1b1d-4b7e-9a51-2a4f0c3d9e11";

const TEST_INFO = {
    test: {
        id: TEST_ID,
        name: "longevity-frobnicator-4h",
        plugin_name: "scylla-cluster-tests",
        build_system_id: "frobnicator/longevity/longevity-frobnicator-4h",
        build_system_url: "https://jenkins.example.com/job/frobnicator",
    },
    release: { id: "r-1", name: "master" },
    group: { id: "g-1", name: "longevity" },
};

const RUNS = [
    {
        id: "a7b1c2d3-0000-4000-8000-000000000412",
        status: "failed",
        build_number: 412,
        start_time: "2026-09-30T22:10:44Z",
    },
];

const respond = (body: unknown, status = 200) => ({ status, json: () => Promise.resolve(body) });

class FakeIntersectionObserver {
    observe() {}
    disconnect() {}
}

beforeEach(() => {
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
    vi.stubGlobal(
        "fetch",
        vi.fn((url: string) => {
            if (url.startsWith("/api/v1/test-info")) return Promise.resolve(respond({ status: "ok", response: TEST_INFO }));
            if (url.startsWith(`/api/v1/test/${TEST_ID}/runs`)) return Promise.resolve(respond({ status: "ok", response: RUNS }));
            return Promise.resolve(respond({}, 404));
        }),
    );
});

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.mocked(TestRunDispatcher).mockClear();
});

const dispatcherProps = () => vi.mocked(TestRunDispatcher).mock.calls.at(-1)?.[1] as Record<string, unknown>;

describe("TestRuns title bar", () => {
    it("shows the title bar by default", async () => {
        render(TestRuns, { props: { testId: TEST_ID, tab: "details" } });

        expect(await screen.findByRole("button", { name: "#412" })).toBeTruthy();
        expect(screen.getByRole("button", { name: /longevity-frobnicator-4h/ })).toBeTruthy();
    });

    it("hides the title bar when showTitleBar is false", async () => {
        render(TestRuns, { props: { testId: TEST_ID, tab: "details", showTitleBar: false } });

        expect(await screen.findByRole("button", { name: "#412" })).toBeTruthy();
        expect(screen.queryByRole("button", { name: /longevity-frobnicator-4h/ })).toBeNull();
        expect(screen.getAllByText("#412")).toHaveLength(1);
    });
});

describe("TestRuns run view", () => {
    it("lets the run view update the URL by default", async () => {
        render(TestRuns, { props: { testId: TEST_ID, tab: "details", additionalRuns: [RUNS[0].id] } });

        await screen.findByRole("button", { name: "#412" });

        expect(dispatcherProps().runId).toBe(RUNS[0].id);
        expect(dispatcherProps().updateUrl).toBe(true);
    });

    it("passes updateUrl false on to the run view", async () => {
        render(TestRuns, { props: { testId: TEST_ID, tab: "details", additionalRuns: [RUNS[0].id], updateUrl: false } });

        await screen.findByRole("button", { name: "#412" });

        expect(dispatcherProps().updateUrl).toBe(false);
    });
});

describe("TestRuns refresh", () => {
    const runListFetches = () =>
        vi.mocked(fetch).mock.calls.filter(([url]) => String(url).startsWith(`/api/v1/test/${TEST_ID}/runs`)).length;

    afterEach(() => {
        vi.useRealTimers();
    });

    it("refreshes the run list every two minutes by default", async () => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        render(TestRuns, { props: { testId: TEST_ID, tab: "details" } });
        await screen.findByRole("button", { name: "#412" });
        expect(runListFetches()).toBe(1);

        await vi.advanceTimersByTimeAsync(120 * 1000);

        expect(runListFetches()).toBe(2);
    });

    it("does not refresh the run list when autoRefresh is false", async () => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        render(TestRuns, { props: { testId: TEST_ID, tab: "details", autoRefresh: false } });
        await screen.findByRole("button", { name: "#412" });

        await vi.advanceTimersByTimeAsync(120 * 1000);

        expect(runListFetches()).toBe(1);
    });

    it("passes autoRefresh on to the run view", async () => {
        render(TestRuns, { props: { testId: TEST_ID, tab: "details", additionalRuns: [RUNS[0].id], autoRefresh: false } });

        await screen.findByRole("button", { name: "#412" });

        expect(dispatcherProps().autoRefresh).toBe(false);
    });
});
