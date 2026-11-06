import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/svelte";

vi.mock("../../../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../../../Common/ApiUtils", () => ({ fetchJson: vi.fn() }));
vi.mock("../../../Stores/UserlistSubscriber.js", () => ({
    userList: {
        subscribe: (fn: (v: unknown) => void) => {
            fn({});
            return () => {};
        },
    },
}));

import { fetchJson } from "../../../Common/ApiUtils";
import ReleaseSummary from "./ReleaseSummary.svelte";
import type { ReleaseSummaryResponse, Summary, SummaryCounts, SummaryIssue, SummaryTest } from "./types";

const counts = (overrides: Partial<SummaryCounts> = {}): SummaryCounts => ({
    executed: 0, passed: 0, failed: 0, aborted: 0, in_progress: 0, pending: 0,
    issues_new: 0, issues_existing: 0, issues_fixed: 0, ...overrides,
});

const test = (name: string, status: string, version: string | null): SummaryTest => ({
    test_id: name, group_id: "g", test_name: name, group_name: "Upgrades", status,
    run_id: version ? `run-${name}` : null, build_id: version ? `job/${name}` : null,
    build_number: version ? 7 : null, version,
});

const issue = (overrides: Partial<SummaryIssue>): SummaryIssue => {
    const base = {
        id: "i1", type: "jira" as const, key: "SCYLLADB-1", title: "Crash on upgrade", url: "https://jira/SCYLLADB-1",
        state: "in progress", novelty: "new" as const, status: "open" as const,
        on_latest_run: (overrides.status ?? "open") === "open", test_ids: ["upgrade"],
        run_ids: ["run-upgrade"], ...overrides,
    };
    return {
        ...base,
        issue: {
            id: base.id, subtype: "jira", key: base.key, summary: base.title, permalink: base.url, state: base.state,
            project: "SCYLLADB", priority: "P1", labels: [], assignees: [], user_id: "u1", event_id: "",
            added_on: "2026-11-01T10:00:00Z",
            links: base.run_ids.map((runId) => ({ id: base.id, run_id: runId, test_id: base.test_ids[0], release_id: "r-1",
                                                  type: "jira", added_on: "2026-11-01T10:00:00Z", user_id: "u1" })),
        } as SummaryIssue["issue"],
    };
};

const RC1: Summary = {
    version: "2025.1.0~rc1",
    counts: counts({ executed: 2, failed: 1, passed: 1, issues_new: 1 }),
    tests: [test("upgrade", "failed", "2025.1.0~rc1"), test("gemini", "passed", "2025.1.0~rc1")],
    issues: [issue({})],
};

const FINAL: Summary = {
    version: "2025.1.0",
    counts: counts({ executed: 1, passed: 1 }),
    tests: [test("upgrade", "passed", "2025.1.0")],
    issues: [],
};

const ROLLUP: Summary = {
    version: null,
    counts: counts({ executed: 2, passed: 2, pending: 1, issues_new: 1, issues_existing: 1, issues_fixed: 1 }),
    tests: [test("upgrade", "passed", "2025.1.0"), test("gemini", "passed", "2025.1.0~rc1"),
            test("longevity", "pending", null)],
    issues: [
        issue({ status: "fixed" }),
        issue({ id: "i2", key: "SCYLLADB-2", title: "Slow compaction", novelty: "existing", state: "open",
                test_ids: ["gemini"], run_ids: ["run-gemini"] }),
    ],
};

const RELEASE: ReleaseSummaryResponse = {
    release_id: "r-1",
    release_name: "scylla-2025.1",
    generated_at: "2026-11-05T09:57:00+00:00",
    stale: false,
    families: [{ family: "2025.1.0", rollup: ROLLUP, versions: [RC1, FINAL] }],
};

const fetchMock = vi.mocked(fetchJson);

beforeEach(() => {
    fetchMock.mockReset();
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-05T10:00:00Z"));
});

afterEach(() => {
    cleanup();
    vi.useRealTimers();
});

const renderRelease = async (props: Record<string, unknown> = {}) => {
    fetchMock.mockResolvedValue(RELEASE);
    render(ReleaseSummary, { props: { dashboardObject: { id: "r-1" }, dashboardObjectType: "release", ...props } });
    await waitFor(() => expect(screen.getByText("Updated 3 minutes ago")).toBeTruthy());
};

describe("ReleaseSummary.svelte", () => {
    it("reads the release route and shows the family timeline with the family row first", async () => {
        await renderRelease();

        expect(fetchMock).toHaveBeenCalledWith("/api/v1/release/r-1/version_summary");
        const timeline = screen.getByRole("table", { name: "Versions of 2025.1.0" });
        const rows = within(timeline).getAllByRole("row").slice(1).map((row) => row.querySelector("th")?.textContent?.trim());
        expect(rows).toEqual(["All of 2025.1.0", "2025.1.0~rc1", "2025.1.0"]);
    });

    it("lists the family tests and narrows them by version and by status", async () => {
        await renderRelease();
        const list = () => screen.getByRole("table", { name: "Tests" });

        expect(within(list()).getByText("longevity")).toBeTruthy();

        await fireEvent.click(screen.getByRole("button", { name: "2025.1.0~rc1" }));
        expect(within(list()).queryByText("longevity")).toBeNull();
        expect(within(list()).getByText("upgrade")).toBeTruthy();

        await fireEvent.click(screen.getByRole("button", { name: "Show the 1 passed tests of 2025.1.0~rc1" }));
        expect(within(list()).queryByText("upgrade")).toBeNull();
        expect(within(list()).getByText("gemini")).toBeTruthy();

        await fireEvent.click(screen.getByRole("button", { name: "Show all statuses" }));
        expect(within(list()).getByText("upgrade")).toBeTruthy();
        expect(screen.queryByRole("button", { name: "Show all statuses" })).toBeNull();
    });

    it("switches each status on and off on its own", async () => {
        await renderRelease();
        const list = () => screen.getByRole("table", { name: "Tests" });
        const pending = screen.getByRole("button", { name: /^Pending/ });

        expect(pending.getAttribute("aria-pressed")).toBe("true");
        await fireEvent.click(pending);

        expect(pending.getAttribute("aria-pressed")).toBe("false");
        expect(within(list()).queryByText("longevity")).toBeNull();
        expect(within(list()).getByText("upgrade")).toBeTruthy();
    });

    it("links a test to its run, or hands it to the popout when the dashboard asks", async () => {
        const onTestClick = vi.fn();
        await renderRelease({ onTestClick });

        await fireEvent.click(within(screen.getByRole("table", { name: "Tests" })).getByRole("button", { name: "upgrade" }));

        expect(onTestClick).toHaveBeenCalledWith(expect.objectContaining({ test_id: "upgrade" }), expect.any(MouseEvent));
        expect(screen.getAllByRole("link", { name: "Open run #7 of upgrade" })[0].getAttribute("href")).toBe("/test/job/upgrade/7");
    });

    it("shows the test by version grid on its tab, with the family issues", async () => {
        await renderRelease();
        await fireEvent.click(screen.getByRole("button", { name: "2025.1.0~rc1" }));

        await fireEvent.click(screen.getByRole("tab", { name: "Grid" }));

        expect(screen.getByRole("heading", { name: "Issues of all of 2025.1.0" })).toBeTruthy();
        expect(screen.getByRole("list", { name: "Open in tracker" })).toBeTruthy();

        const grid = screen.getByRole("table", { name: "Tests by version of 2025.1.0" });
        expect(within(grid).getAllByRole("columnheader").map((cell) => cell.textContent?.trim())).toEqual(
            ["Test", "2025.1.0~rc1", "2025.1.0"]);
        const upgrade = within(grid).getByRole("rowheader", { name: /upgrade/ }).closest("tr")!;
        expect(within(upgrade).getByTitle("2025.1.0~rc1: failed, run #7")).toBeTruthy();
        expect(within(upgrade).getByTitle("2025.1.0: passed, run #7")).toBeTruthy();
    });

    it("marks only the issues linked to a latest run", async () => {
        const family = { ...ROLLUP, issues: [issue({ title: "Seen on this rc only", on_latest_run: false })] };
        fetchMock.mockResolvedValue({ ...RELEASE, families: [{ family: "2025.1.0", rollup: family, versions: [RC1, FINAL] }] });
        render(ReleaseSummary, { props: { dashboardObject: { id: "r-1" }, dashboardObjectType: "release" } });
        await screen.findByText("Updated 3 minutes ago");

        expect(screen.getByText("Seen on this rc only")).toBeTruthy();
        expect(screen.queryByText("on latest run")).toBeNull();
    });

    it("groups the issues by tracker state and says which are on a latest run", async () => {
        const family = {
            ...ROLLUP,
            issues: [
                issue({ id: "i3", key: "SCYLLADB-3", title: "Done but back", state: "done", status: "open" }),
                issue({ status: "fixed", state: "done" }),
                ROLLUP.issues[1],
            ],
        };
        fetchMock.mockResolvedValue({ ...RELEASE, families: [{ family: "2025.1.0", rollup: family, versions: [RC1, FINAL] }] });
        render(ReleaseSummary, { props: { dashboardObject: { id: "r-1" }, dashboardObjectType: "release" } });
        await screen.findByText("Updated 3 minutes ago");

        const open = screen.getByRole("list", { name: "Open in tracker" });
        const closed = screen.getByRole("list", { name: "Closed in tracker" });
        expect(within(open).getByText("Slow compaction")).toBeTruthy();
        expect(within(open).getByText("existing")).toBeTruthy();
        expect(within(open).getByText("on latest run")).toBeTruthy();
        expect(within(open).queryByText("Done but back")).toBeNull();
        const closedRows = within(closed).getAllByRole("listitem");
        expect(within(closedRows[0]).getByText("Done but back")).toBeTruthy();
        expect(within(closedRows[0]).getByText("on latest run")).toBeTruthy();
        expect(within(closed).queryByText(/closed but/)).toBeNull();
        expect(within(closedRows[1]).getByText("Crash on upgrade")).toBeTruthy();
        expect(within(closedRows[1]).getByText("last seen rc1")).toBeTruthy();
    });

    it("expands an issue row into the full issue card", async () => {
        await renderRelease();
        const open = screen.getByRole("list", { name: "Open in tracker" });

        expect(within(open).queryByRole("button", { name: "View 1 runs" })).toBeNull();
        await fireEvent.click(within(open).getByRole("button", { name: "Show details of SCYLLADB-2" }));

        expect(within(open).getByRole("button", { name: "View 1 runs" })).toBeTruthy();
        expect(within(open).queryByRole("button", { name: "Add to current run" })).toBeNull();
    });

    it("starts collapsed on the release dashboard with the family figures in the header", async () => {
        fetchMock.mockResolvedValue(RELEASE);
        render(ReleaseSummary, { props: { dashboardObject: { id: "r-1" }, dashboardObjectType: "release", collapsible: true } });

        const header = await screen.findByRole("button", { name: /Release summary/ });
        await waitFor(() => expect(within(header).getByText("2025.1.0")).toBeTruthy());
        expect(header.getAttribute("aria-expanded")).toBe("false");
        expect(screen.queryByRole("table", { name: "Tests" })).toBeNull();

        await fireEvent.click(header);

        expect(header.getAttribute("aria-expanded")).toBe("true");
        expect(screen.getByRole("table", { name: "Tests" })).toBeTruthy();
    });

    it("opens a family from anywhere on its header, and a bar segment filters without closing it", async () => {
        fetchMock.mockResolvedValue({
            ...RELEASE,
            families: [...RELEASE.families, { family: "2024.1.0", rollup: ROLLUP, versions: [RC1] }],
        });
        render(ReleaseSummary, { props: { dashboardObject: { id: "r-1" }, dashboardObjectType: "release" } });
        const older = await screen.findByRole("region", { name: "Family 2024.1.0" });
        const toggle = within(older).getByRole("button", { name: "Expand 2024.1.0" });

        await fireEvent.click(within(older).getByText(/3 tests · 2 executed/));
        expect(toggle.getAttribute("aria-expanded")).toBe("true");

        await fireEvent.click(within(older).getByText(/3 tests · 2 executed/));
        expect(toggle.getAttribute("aria-expanded")).toBe("false");

        await fireEvent.click(within(older).getAllByRole("button", { name: "Show the 2 passed tests" })[0]);
        expect(toggle.getAttribute("aria-expanded")).toBe("true");
        expect(within(older).getByRole("button", { name: /^Passed/ }).getAttribute("aria-pressed")).toBe("true");
    });

    it("reads the view route and names each release", async () => {
        fetchMock.mockResolvedValue({ releases: [RELEASE] });

        render(ReleaseSummary, { props: { dashboardObject: { id: "v-1" }, dashboardObjectType: "view" } });

        await waitFor(() => expect(screen.getByRole("heading", { name: "scylla-2025.1" })).toBeTruthy());
        expect(fetchMock).toHaveBeenCalledWith("/api/v1/views/widgets/release_summary?view_id=v-1");
    });

    it("refreshes stored figures until the recompute lands, and says when nothing was tested", async () => {
        vi.useFakeTimers({ toFake: ["Date", "setTimeout"] });
        vi.setSystemTime(new Date("2026-11-05T10:00:00Z"));
        fetchMock.mockResolvedValueOnce({ releases: [{ ...RELEASE, stale: true }, { ...RELEASE, release_id: "r-2", families: [] }] })
            .mockResolvedValue({ releases: [RELEASE, { ...RELEASE, release_id: "r-2", families: [] }] });

        render(ReleaseSummary, { props: { dashboardObject: { id: "v-2" } } });

        await waitFor(() => expect(screen.getByText(/Refreshing; showing the figures stored/)).toBeTruthy());
        expect(screen.getByText("No tested or planned versions yet.")).toBeTruthy();
        await vi.advanceTimersByTimeAsync(3000);
        await waitFor(() => expect(screen.queryByText(/Refreshing/)).toBeNull());
        expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it("says when the stored figures could not be refreshed", async () => {
        vi.useFakeTimers({ toFake: ["Date", "setTimeout"] });
        vi.setSystemTime(new Date("2026-11-05T10:00:00Z"));
        fetchMock.mockResolvedValue({ ...RELEASE, stale: true });

        render(ReleaseSummary, { props: { dashboardObject: { id: "r-1" }, dashboardObjectType: "release" } });
        for (let tries = 0; tries < 5; tries += 1) {
            await vi.advanceTimersByTimeAsync(3000);
        }

        await waitFor(() => expect(screen.getByText(/could not be refreshed/)).toBeTruthy());
        expect(fetchMock).toHaveBeenCalledTimes(6);
    });

    it("shows the findings of the view and of each release", async () => {
        const finding = (id: string, content: string) => ({ id, content, updated_by: "u1",
                                                            updated_at: new Date().toISOString(), source_node: "n1" });
        fetchMock.mockResolvedValue({ releases: [{ ...RELEASE, findings: [finding("f1", "rc3 failures are infra")] }],
                                      findings: [finding("f2", "Week1 runs on GCE only")] });

        render(ReleaseSummary, { props: { dashboardObject: { id: "v-3" } } });

        await waitFor(() => expect(screen.getByText("rc3 failures are infra")).toBeTruthy());
        expect(screen.getByText("Week1 runs on GCE only")).toBeTruthy();
        expect(screen.getAllByRole("region", { name: "Findings" })).toHaveLength(2);
    });
});

describe("the test list counts", () => {
    it("shows the issues and comments of each test's run", async () => {
        const counted = { ...RELEASE, families: [{ ...RELEASE.families[0], rollup: { ...RELEASE.families[0].rollup,
            tests: [{ ...test("upgrade", "failed", "2025.1.0~rc1"), issues: 2, comments: 3 },
                    { ...test("gemini", "passed", "2025.1.0~rc1"), issues: 0, comments: 0 },
                    test("pending-one", "pending", null)] } }] };
        fetchMock.mockResolvedValue(counted);
        render(ReleaseSummary, { props: { dashboardObject: { id: "r-1" }, dashboardObjectType: "release" } });
        await waitFor(() => expect(screen.getByText("Updated 3 minutes ago")).toBeTruthy());

        expect(await screen.findByLabelText("2 issues")).toBeTruthy();
        expect(screen.getByLabelText("3 comments")).toBeTruthy();
    });
});
