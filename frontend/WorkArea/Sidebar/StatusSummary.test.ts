import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup, screen } from "@testing-library/svelte";
import StatusSummary from "./StatusSummary.svelte";

afterEach(() => cleanup());

describe("StatusSummary", () => {
    it("draws one segment per status that has runs, worst first", () => {
        const { container } = render(StatusSummary, {
            props: { stats: { total: 10, passed: 6, failed: 2, not_run: 2, running: 0, to_investigate: 1 } },
        });

        const segments = [...container.querySelectorAll(".status-bar > div")] as HTMLElement[];
        expect(segments.map((segment) => segment.classList[0])).toEqual(["bg-danger", "bg-success", "bg-secondary"]);
        expect(segments.map((segment) => segment.style.width)).toEqual(["20%", "60%", "20%"]);
    });

    it("describes the whole breakdown for assistive technology", () => {
        render(StatusSummary, {
            props: { stats: { total: 10, passed: 6, failed: 2, not_run: 2, to_investigate: 1 } },
        });

        expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
            "2 failed, 6 passed, 2 not run, 1 to investigate of 10"
        );
    });

    it("counts failed, test errors and errors together", () => {
        render(StatusSummary, { props: { stats: { total: 4, failed: 1, test_error: 1, error: 1, passed: 1 } } });

        expect(screen.getByText("3")).toBeTruthy();
    });

    it("renders nothing for an empty release", () => {
        const { container } = render(StatusSummary, { props: { stats: { total: 0 } } });

        expect(container.querySelector("[role=img]")).toBeNull();
    });
});
