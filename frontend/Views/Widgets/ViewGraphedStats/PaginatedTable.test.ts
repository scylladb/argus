import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/svelte";
import PaginatedTable from "./PaginatedTable.svelte";
import type { TestRun } from "./Interfaces";

afterEach(() => cleanup());

function makeRun(overrides: Partial<TestRun> = {}): TestRun {
    return {
        build_id: "build-1",
        version: "5.2.0",
        status: "passed",
        duration: 120,
        run_id: "run-1",
        start_time: 1700000000,
        investigation_status: "not_investigated",
        ...overrides,
    };
}

const baseColumns = [
    { key: "status", label: "Status", sort: (a: any, b: any) => a.status.localeCompare(b.status) },
    { key: "version", label: "Version" },
    { key: "build_id", label: "Build" },
];

function renderTable(props: Partial<Parameters<typeof render>[1]> & { items: any[] }) {
    return render(PaginatedTable, {
        props: {
            title: "Test Table",
            sortField: "status",
            sortDirection: "asc" as const,
            columns: baseColumns,
            onClose: vi.fn(),
            ...props,
        },
    });
}

describe("PaginatedTable", () => {
    it("renders column headers from columns prop", () => {
        renderTable({ items: [makeRun()] });

        expect(screen.getByText("Status")).toBeTruthy();
        expect(screen.getByText("Version")).toBeTruthy();
        expect(screen.getByText("Build")).toBeTruthy();
    });

    it("renders the title", () => {
        renderTable({ items: [makeRun()], title: "Nemesis Runs" });
        expect(screen.getByText("Nemesis Runs")).toBeTruthy();
    });

    it("renders correct number of data rows", () => {
        const items = [
            makeRun({ build_id: "b1", status: "passed" }),
            makeRun({ build_id: "b2", status: "failed" }),
            makeRun({ build_id: "b3", status: "error" }),
        ];

        const { container } = renderTable({ items });

        const rows = container.querySelectorAll("tbody tr");
        expect(rows).toHaveLength(3);
    });

    it("paginates when items exceed itemsPerPage", () => {
        const items = Array.from({ length: 5 }, (_, i) => makeRun({ build_id: `b${i}`, run_id: `r${i}` }));

        const { container } = renderTable({ items, itemsPerPage: 2 });

        // Only 2 rows visible on first page
        const rows = container.querySelectorAll("tbody tr");
        expect(rows).toHaveLength(2);

        // Pagination controls present (3 pages for 5 items / 2 per page)
        expect(screen.getByText("Previous")).toBeTruthy();
        expect(screen.getByText("Next")).toBeTruthy();
        expect(screen.getByText("3")).toBeTruthy();
    });

    it("does not show pagination when all items fit on one page", () => {
        const { container } = renderTable({ items: [makeRun()], itemsPerPage: 20 });

        const nav = container.querySelector("nav");
        expect(nav).toBeNull();
    });

    it("displays cell values from item properties", () => {
        const { container } = renderTable({
            items: [makeRun({ status: "failed", version: "6.0.0", build_id: "special-build" })],
        });

        const cells = container.querySelectorAll("tbody td");
        const texts = Array.from(cells).map((c) => c.textContent?.trim());
        expect(texts).toContain("failed");
        expect(texts).toContain("6.0.0");
        expect(texts).toContain("special-build");
    });

    it("calls onClose when close button is clicked", () => {
        const onClose = vi.fn();
        const { container } = renderTable({ items: [makeRun()], onClose });

        const closeBtn = container.querySelector("button.btn-outline-secondary") as HTMLButtonElement;
        closeBtn.click();
        expect(onClose).toHaveBeenCalledOnce();
    });
});
