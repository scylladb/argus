import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import TopRuns from "./TopRuns.svelte";

const RUN = {
    run_id: "r-1",
    build_id: "scylla-master/longevity/longevity-100gb-4h",
    build_number: 12,
    plugin_name: "scylla-cluster-tests",
    release: "2026.1",
    group: "longevity",
    test: "longevity-100gb-4h",
    status: "failed",
    start_time: "2026-10-05T10:00:00Z",
    end_time: "2026-10-05T14:30:00Z",
    backend: "aws",
    region: "eu-west-1",
    spend: 812.4,
    coverage: "partial" as const,
    spot_terminated: true,
    started_by: "alice",
};

afterEach(cleanup);

describe("TopRuns.svelte", () => {
    it("links each run by its build and shows its badges", () => {
        render(TopRuns, { props: { runs: [RUN, { ...RUN, run_id: "r-2", build_number: null, end_time: null, spend: 10, coverage: "complete", spot_terminated: false }] } });

        const link = screen.getByRole("link", { name: "longevity-100gb-4h" });
        expect(link.getAttribute("href")).toBe("/test/scylla-master/longevity/longevity-100gb-4h/12");
        expect(screen.getAllByRole("link")).toHaveLength(1);
        expect(screen.getByText("$812.40")).toBeTruthy();
        expect(screen.getByText("4h 30m")).toBeTruthy();
        expect(screen.getByText("Partial")).toBeTruthy();
        expect(screen.getByText("Spot reclaimed")).toBeTruthy();
        expect(screen.getByText("Complete")).toBeTruthy();
    });

    it("sorts by a clicked column and flips on a second click", async () => {
        render(TopRuns, { props: { runs: [
            { ...RUN, run_id: "r-1", test: "beta", spend: 10 },
            { ...RUN, run_id: "r-2", test: "alpha", spend: 20 },
        ] } });
        const tests = () => screen.getAllByRole("link").map((link) => link.textContent);

        expect(tests()).toEqual(["alpha", "beta"]);
        await fireEvent.click(screen.getByRole("button", { name: /^Test/ }));
        expect(tests()).toEqual(["alpha", "beta"]);
        await fireEvent.click(screen.getByRole("button", { name: /^Test/ }));
        expect(tests()).toEqual(["beta", "alpha"]);
    });

    it("shows who started each run, and a dash when nobody is recorded", () => {
        render(TopRuns, { props: { runs: [RUN, { ...RUN, run_id: "r-2", spend: 10, started_by: null }] } });

        const rows = screen.getAllByRole("row").slice(1);
        expect(rows[0].textContent).toContain("alice");
        expect(rows[1].querySelectorAll("td")[4].textContent).toBe("—");
    });

    it("sorts by who started the run", async () => {
        render(TopRuns, { props: { runs: [
            { ...RUN, run_id: "r-1", test: "first", started_by: "bob", spend: 30 },
            { ...RUN, run_id: "r-2", test: "second", started_by: null, spend: 20 },
            { ...RUN, run_id: "r-3", test: "third", started_by: "alice", spend: 10 },
        ] } });
        const tests = () => screen.getAllByRole("link").map((link) => link.textContent);

        await fireEvent.click(screen.getByRole("button", { name: /^Started by/ }));
        expect(tests()).toEqual(["third", "first", "second"]);
        await fireEvent.click(screen.getByRole("button", { name: /^Started by/ }));
        expect(tests()).toEqual(["second", "first", "third"]);
    });

    it("states the empty range", () => {
        render(TopRuns, { props: { runs: [] } });

        expect(screen.getByText("No priced run in this range.")).toBeTruthy();
    });
});
