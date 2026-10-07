import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/svelte";

import GenericTestRunInfo from "./GenericTestRunInfo.svelte";

const RUN = {
    id: "7f3e2a6c-5b1d-4c8e-9a0f-2d4b6c8e0a1f",
    build_id: "local-runs/jdoe/my-argus-local-run",
    build_job_url: "",
    started_by: "jdoe",
    status: "passed",
    start_time: "2026-10-06T10:00:00Z",
    end_time: "2026-10-06T11:00:00Z",
};

const HIERARCHY = {
    release: { name: "local-runs" },
    group: { name: "jdoe" },
    test: { name: "my-argus-local-run" },
};

const SOURCE = "91c226dc-a057-4ad4-a0b8-bf8bc73031b9";

function stubRunType(runType: string) {
    const fetchSpy = vi.fn().mockResolvedValue({
        json: () => Promise.resolve({ status: "ok", response: { run_type: runType } }),
    });
    vi.stubGlobal("fetch", fetchSpy);
    return fetchSpy;
}

afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
});

describe("GenericTestRunInfo.svelte", () => {
    it("links a replayed run to its source when Argus has the source", async () => {
        const fetchSpy = stubRunType("generic");
        render(GenericTestRunInfo, { props: { ...HIERARCHY, test_run: { ...RUN, source_run_id: SOURCE } } });

        expect(fetchSpy).toHaveBeenCalledWith(`/api/v1/run/${SOURCE}/type`);
        const link = await waitFor(() => screen.getByRole("link", { name: SOURCE }));
        expect(link.getAttribute("href")).toBe(`/test_run/${SOURCE}`);
    });

    it("names a source that never reached Argus without a link", async () => {
        stubRunType("unknown-does-not-exist");
        render(GenericTestRunInfo, { props: { ...HIERARCHY, test_run: { ...RUN, source_run_id: SOURCE } } });

        await waitFor(() => expect(screen.getByText("(not in Argus)")).toBeTruthy());
        expect(screen.getByText("Replayed from:")).toBeTruthy();
        expect(screen.queryByRole("link", { name: SOURCE })).toBeNull();
    });

    it("claims nothing about the source while the lookup fails", async () => {
        const fetchSpy = vi.fn().mockRejectedValue(new Error("network down"));
        vi.stubGlobal("fetch", fetchSpy);
        render(GenericTestRunInfo, { props: { ...HIERARCHY, test_run: { ...RUN, source_run_id: SOURCE } } });

        await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
        expect(screen.getByText(SOURCE)).toBeTruthy();
        expect(screen.queryByText("(not in Argus)")).toBeNull();
        expect(screen.queryByRole("link", { name: SOURCE })).toBeNull();
    });

    it("shows no replay line for a run that was not replayed", () => {
        const fetchSpy = stubRunType("generic");
        render(GenericTestRunInfo, { props: { ...HIERARCHY, test_run: { ...RUN, source_run_id: null } } });

        expect(screen.queryByText("Replayed from:")).toBeNull();
        expect(fetchSpy).not.toHaveBeenCalled();
    });
});
