import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";

vi.mock("../WorkArea/TestRuns.svelte", () => ({ default: vi.fn() }));
vi.mock("svelte/transition", () => ({ slide: () => ({ duration: 0 }) }));

import TestRuns from "../WorkArea/TestRuns.svelte";
import LinkedRun from "./LinkedRun.svelte";

afterEach(() => {
    cleanup();
    vi.mocked(TestRuns).mockClear();
});

const LINK = {
    run_id: "a7b1c2d3-0000-4000-8000-000000000412",
    test_id: "6f0c3a52-1b1d-4b7e-9a51-2a4f0c3d9e11",
    test_name: "longevity-frobnicator-4h",
    plugin_name: "scylla-cluster-tests",
    status: "failed",
    start_time: "2026-09-30T22:10:44Z",
    build_id: "frobnicator/longevity/longevity-frobnicator-4h",
    build_number: 412,
    scylla_version: "2026.2.0~dev",
    product_version: "2026.2.0~dev",
    linked_on: "2026-10-01T07:02:13Z",
    url: "http://testserver/test/frobnicator/longevity/longevity-frobnicator-4h/412",
};

const lastTestRunsProps = () => vi.mocked(TestRuns).mock.calls.at(-1)?.[1] as Record<string, unknown>;

describe("LinkedRun", () => {
    it("shows the run summary", () => {
        render(LinkedRun, { props: { link: LINK } });

        expect(screen.getByText("longevity-frobnicator-4h")).toBeTruthy();
        expect(screen.getByText("#412")).toBeTruthy();
        expect(screen.getByText("2026.2.0~dev")).toBeTruthy();
        expect(screen.getByText("frobnicator/longevity · linked 2026-10-01 07:02")).toBeTruthy();
        expect(screen.getByText("Failed")).toBeTruthy();
    });

    it("falls back to the product version", () => {
        render(LinkedRun, { props: { link: { ...LINK, scylla_version: null, product_version: "2026.1.3" } } });

        expect(screen.getByText("2026.1.3")).toBeTruthy();
    });

    it("links to the run page", () => {
        render(LinkedRun, { props: { link: LINK } });

        expect(screen.getByRole("link", { name: /Open run/ }).getAttribute("href")).toBe(LINK.url);
    });

    it("opens the run inline", async () => {
        render(LinkedRun, { props: { link: LINK } });
        const toggle = screen.getByRole("button", { name: /Show inline/ });

        await fireEvent.click(toggle);

        expect(toggle.getAttribute("aria-expanded")).toBe("true");
        expect(TestRuns).toHaveBeenCalledTimes(1);
        const props = lastTestRunsProps();
        expect(props.testId).toBe(LINK.test_id);
        expect(props.additionalRuns).toEqual([LINK.run_id]);
        expect(props.tab).toBe("details");
        expect(props.showTitleBar).toBe(false);
        expect(props.updateUrl).toBe(false);

        await fireEvent.click(toggle);

        expect(toggle.getAttribute("aria-expanded")).toBe("false");

        await fireEvent.click(toggle);

        expect(TestRuns).toHaveBeenCalledTimes(2);
    });
});
