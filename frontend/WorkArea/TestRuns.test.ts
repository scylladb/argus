import { describe, it, expect, vi, afterEach } from "vitest";
import { render, cleanup, waitFor } from "@testing-library/svelte";

vi.mock("../argus", () => ({ applicationCurrentUser: { roles: [] } }));
vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));

import TestRuns from "./TestRuns.svelte";

const ok = (response: unknown) => Promise.resolve({ status: 200, json: () => Promise.resolve({ status: "ok", response }) });

const TEST_INFO = {
    test: { id: "t1", name: "alpha-test", plugin_name: "scylla-cluster-tests", build_system_id: "rel/alpha-test" },
    group: { id: "g1", name: "group" },
    release: { id: "rel", name: "rel" },
};

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});

describe("TestRuns", () => {
    it("fetches the runs again when a run is picked into the open test", async () => {
        const fetchMock = vi.fn((url: string) => (url.startsWith("/api/v1/test-info") ? ok(TEST_INFO) : ok([])));
        vi.stubGlobal("fetch", fetchMock);
        const runsRequests = () => fetchMock.mock.calls.map(([url]) => url as string).filter((url) => url.includes("/runs?"));
        const { rerender } = render(TestRuns, { props: { testId: "t1", tab: null, additionalRuns: ["r1"] } });
        await waitFor(() => expect(runsRequests()).toHaveLength(1));

        await rerender({ testId: "t1", tab: null, additionalRuns: ["r1", "r2"] });

        await waitFor(() => expect(runsRequests()).toHaveLength(2));
        expect(runsRequests()[1]).toContain("additionalRuns[]=r2");
    });
});
