import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor, within, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";

// AlertStore and child-component stores must be mocked before the component
// is imported so Svelte's module evaluation picks up the stubs.
vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../Stores/UserlistSubscriber.js", () => ({
    userList: {
        subscribe: (fn: (v: unknown) => void) => {
            fn({});
            return () => {};
        },
    },
}));

import Issues from "./Issues.svelte";
import type { GithubSubtype, JiraSubtype, Label } from "../Common/IssueTypes";

// ---------------------------------------------------------------------------
// Module-level fixtures
// ---------------------------------------------------------------------------

// A minimal successful API response with no issues — enough to reach the
// empty-state branch without rendering child GithubIssue / JiraIssue components.
const EMPTY_OK_RESPONSE = { json: () => Promise.resolve({ status: "ok", response: [] }) };

const BASE_PROPS = {
    runId: "run-1",
    testId: "test-1",
    pluginName: "scylla-cluster-tests",
    id: "run-1",
    submitDisabled: true, // hides the issue-submission form; keeps render minimal
} as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderIssues(extraProps: Record<string, unknown> = {}) {
    return render(Issues, { props: { ...BASE_PROPS, ...extraProps } });
}

// Pull the URL string that fetch was called with out of the spy.
function capturedUrl(fetchSpy: ReturnType<typeof vi.fn>, callIndex = 0): string {
    return fetchSpy.mock.calls[callIndex][0] as string;
}

// Wait until the component has settled after a fetch: the empty-state text is
// visible, meaning fetching=false and issues=[] have been written back to $state.
// After this point, any spurious $effect re-run would have already fired.
async function waitForFetchToSettle(emptyStateText = "No issues found.") {
    await waitFor(() => expect(screen.getByText(emptyStateText)).toBeTruthy());
    // Flush any remaining microtasks / Svelte scheduler ticks.
    await tick();
    await tick();
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Issues.svelte — productVersion filtering", () => {
    let fetchSpy: ReturnType<typeof vi.fn>;

    beforeEach(() => {
        fetchSpy = vi.fn().mockResolvedValue(EMPTY_OK_RESPONSE);
        vi.stubGlobal("fetch", fetchSpy);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        cleanup();
    });

    // --- no spurious re-fetch after mount -----------------------------------

    // NOTE: This test attempts to catch the $effect re-run bug where calling
    // fetchIssues() without untrack() causes the effect to re-run after
    // issues/fetching $state is written back. In jsdom the Svelte scheduler
    // coalesces microtasks fast enough that the spurious call may not be
    // observable within waitFor's timeout, so this test is a best-effort
    // guard rather than a guaranteed regression detector for that specific bug.
    it("fetches exactly once on mount and does not re-fetch after state settles", async () => {
        renderIssues({ productVersion: "6.2.0" });
        await waitForFetchToSettle("No issues linked for version 6.2.0.");
        expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    // --- query-string construction ------------------------------------------

    it("omits productVersion and includeNoVersion from the request when productVersion is not set", async () => {
        renderIssues();
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

        const url = capturedUrl(fetchSpy);
        expect(url).not.toContain("productVersion");
        expect(url).not.toContain("includeNoVersion");
    });

    it("includes productVersion in the request when the prop is provided", async () => {
        renderIssues({ productVersion: "6.2.0" });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

        expect(capturedUrl(fetchSpy)).toContain("productVersion=6.2.0");
    });

    it.each([
        {
            productVersion: "6.2.0",
            includeNoVersion: false,
            shouldInclude: false,
            label: "omits includeNoVersion when false",
        },
        {
            productVersion: "6.2.0",
            includeNoVersion: true,
            shouldInclude: true,
            label: "includes includeNoVersion=1 when true",
        },
    ])("$label", async ({ productVersion, includeNoVersion, shouldInclude }) => {
        renderIssues({ productVersion, includeNoVersion });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

        const url = capturedUrl(fetchSpy);
        if (shouldInclude) {
            expect(url).toContain("includeNoVersion=1");
        } else {
            expect(url).not.toContain("includeNoVersion");
        }
    });

    it("omits includeNoVersion even when true if productVersion is not set", async () => {
        renderIssues({ includeNoVersion: true });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

        expect(capturedUrl(fetchSpy)).not.toContain("includeNoVersion");
    });

    // --- reactive re-fetch --------------------------------------------------

    it("re-fetches when productVersion prop changes", async () => {
        const { rerender } = renderIssues({ productVersion: "6.1.0" });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

        await rerender({ props: { ...BASE_PROPS, productVersion: "6.2.0" } });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));

        expect(capturedUrl(fetchSpy, 1)).toContain("productVersion=6.2.0");
    });

    it("re-fetches when includeNoVersion prop changes", async () => {
        const { rerender } = renderIssues({ productVersion: "6.2.0", includeNoVersion: false });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));

        await rerender({ props: { ...BASE_PROPS, productVersion: "6.2.0", includeNoVersion: true } });
        await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));

        expect(capturedUrl(fetchSpy, 1)).toContain("includeNoVersion=1");
    });

    // --- empty-state messages -----------------------------------------------
    it.each([
        {
            productVersion: "6.2.0",
            expected: "No issues linked for version 6.2.0.",
            label: "named version",
        },
        {
            productVersion: "!noVersion",
            expected: "No issues linked for version runs without a version.",
            label: "!noVersion sentinel",
        },
    ])("shows version-specific empty-state for $label", async ({ productVersion, expected }) => {
        renderIssues({ productVersion });
        await waitFor(() => expect(screen.getByText(expected)).toBeTruthy());
    });

    it("shows generic empty-state when productVersion is not set", async () => {
        renderIssues();
        await waitFor(() => expect(screen.getByText("No issues found.")).toBeTruthy());
    });
});

// ---------------------------------------------------------------------------
// Filters, labels and sorting over fetched issues
// ---------------------------------------------------------------------------

const label = (id: string, name: string, color = "d73a4a"): Label => ({ id, name, color, description: "" });

const githubIssue = (number: number, title: string, state: "open" | "closed", extra: Partial<GithubSubtype> = {}): GithubSubtype => ({
    subtype: "github",
    id: `g-${number}`,
    state,
    event_id: "",
    added_on: "2026-10-01T10:00:00Z",
    labels: [],
    user_id: "u-1",
    links: [],
    repo: "quux-fake-repo",
    owner: "xyzzy-fake-org",
    number: String(number),
    title,
    url: `https://github.com/xyzzy-fake-org/quux-fake-repo/issues/${number}`,
    assignees: [],
    ...extra,
});

const jiraIssue = (key: string, summary: string, state: string, priority: string | null, extra: Partial<JiraSubtype> = {}): JiraSubtype => ({
    subtype: "jira",
    id: `j-${key}`,
    state: state as JiraSubtype["state"],
    event_id: "",
    added_on: "2026-10-01T10:00:00Z",
    labels: [],
    user_id: "u-2",
    links: [],
    key,
    summary,
    project: key.split("-")[0],
    priority,
    permalink: `https://zxqtesting.atlassian.net/browse/${key}`,
    assignees: [],
    ...extra,
});

const MIXED_ISSUES = [
    githubIssue(1, "GitHub open issue", "open"),
    githubIssue(2, "GitHub closed issue", "closed"),
    jiraIssue("SCT-10", "SCT todo P1", "to do", "P1"),
    jiraIssue("SCYLLADB-20", "Scylla in progress P0", "in progress", "P0"),
    jiraIssue("SCT-30", "SCT done without priority", "done", null),
];

const ALL_TITLES = /^(GitHub open issue|GitHub closed issue|SCT todo P1|Scylla in progress P0|SCT done without priority|Labelled bug one|Labelled bug two|Labelled perf|Jira P2|Jira P0|GitHub newest|Jira without priority)$/;

const shownTitles = () => screen.queryAllByText(ALL_TITLES).map((el) => el.textContent);

const optionNames = (group: string) =>
    within(screen.getByRole("group", { name: group }))
        .getAllByRole("checkbox")
        .map((box) => box.closest(".form-check")?.textContent?.trim());

async function renderWith(issues: unknown[]) {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ json: () => Promise.resolve({ status: "ok", response: issues }) }));
    renderIssues({ submitDisabled: true });
    await waitFor(() => expect(shownTitles().length).toBeGreaterThan(0));
}

describe("Issues.svelte — checkbox filters", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
        cleanup();
    });

    it("lists every status, priority and Jira Space of the fetched issues", async () => {
        await renderWith(MIXED_ISSUES);

        expect(optionNames("Status")).toEqual(["closed", "done", "in progress", "open", "to do"]);
        expect(optionNames("Priority")).toEqual(["P0", "P1", "none"]);
        expect(optionNames("Space")).toEqual(["SCT", "SCYLLADB"]);
        expect(shownTitles()).toHaveLength(5);
    });

    it("hides the issues of an unchecked status", async () => {
        await renderWith(MIXED_ISSUES);

        await fireEvent.click(within(screen.getByRole("group", { name: "Status" })).getByLabelText("to do"));

        expect(shownTitles()).not.toContain("SCT todo P1");
        expect(shownTitles()).toHaveLength(4);
    });

    it("hides the Jira issues of an unchecked Space and keeps the GitHub issues", async () => {
        await renderWith(MIXED_ISSUES);

        await fireEvent.click(within(screen.getByRole("group", { name: "Space" })).getByLabelText("SCT"));

        expect(shownTitles().sort()).toEqual(["GitHub closed issue", "GitHub open issue", "Scylla in progress P0"]);
    });

    it("hides the Jira issues without a priority when none is unchecked", async () => {
        await renderWith(MIXED_ISSUES);

        await fireEvent.click(within(screen.getByRole("group", { name: "Priority" })).getByLabelText("none"));

        expect(shownTitles()).not.toContain("SCT done without priority");
        expect(shownTitles()).toHaveLength(4);
    });

    it("shows the issues again when the box is checked again", async () => {
        await renderWith(MIXED_ISSUES);
        const box = within(screen.getByRole("group", { name: "Priority" })).getByLabelText("P0");

        await fireEvent.click(box);
        expect(shownTitles()).toHaveLength(4);
        await fireEvent.click(box);

        expect(shownTitles()).toHaveLength(5);
    });

    it("renders no Priority and no Space group for GitHub issues only", async () => {
        await renderWith(MIXED_ISSUES.filter((issue) => issue.subtype === "github"));

        expect(optionNames("Status")).toEqual(["closed", "open"]);
        expect(screen.queryByRole("group", { name: "Priority" })).toBeNull();
        expect(screen.queryByRole("group", { name: "Space" })).toBeNull();
    });
});

describe("Issues.svelte — All Labels panel", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
        cleanup();
    });

    const LABELLED_ISSUES = [
        githubIssue(1, "Labelled bug one", "open", { labels: [label("11", "bug")] }),
        jiraIssue("SCT-2", "Labelled bug two", "to do", "P2", { labels: [label("33", "bug", "000")] }),
        jiraIssue("SCT-3", "Labelled perf", "to do", "P2", { labels: [label("22", "perf", "000")] }),
    ];

    const panel = () => screen.getByRole("group", { name: "All labels" });

    it("lists each label of the fetched issues once", async () => {
        await renderWith(LABELLED_ISSUES);

        expect(within(panel()).getAllByRole("button").map((button) => button.textContent?.trim())).toEqual(["bug", "perf"]);
    });

    it("filters by a label picked in the panel and restores the list when it is picked again", async () => {
        await renderWith(LABELLED_ISSUES);
        const perf = within(panel()).getByRole("button", { name: "perf" });

        await fireEvent.click(perf);
        expect(shownTitles()).toEqual(["Labelled perf"]);
        expect(perf.getAttribute("aria-pressed")).toBe("true");

        await fireEvent.click(perf);
        expect(shownTitles()).toHaveLength(3);
        expect(perf.getAttribute("aria-pressed")).toBe("false");
    });

    it("matches a label by name across trackers", async () => {
        await renderWith(LABELLED_ISSUES);

        await fireEvent.click(within(panel()).getByRole("button", { name: "bug" }));

        expect(shownTitles().sort()).toEqual(["Labelled bug one", "Labelled bug two"]);
    });

    it("renders no panel when the issues carry no labels", async () => {
        await renderWith(MIXED_ISSUES);

        expect(screen.queryByRole("group", { name: "All labels" })).toBeNull();
        expect(screen.queryByText(/All Labels/)).toBeNull();
    });
});

describe("Issues.svelte — sorting by priority", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
        cleanup();
    });

    const PRIORITY_ISSUES = [
        jiraIssue("SCT-1", "Jira P2", "to do", "P2", { added_on: "2026-10-01T10:00:00Z" }),
        jiraIssue("SCT-2", "Jira P0", "to do", "P0", { added_on: "2026-10-02T10:00:00Z" }),
        githubIssue(3, "GitHub newest", "open", { added_on: "2026-10-05T10:00:00Z" }),
        jiraIssue("SCT-4", "Jira without priority", "to do", null, { added_on: "2026-10-03T10:00:00Z" }),
    ];

    it("puts P0 first and the issues without a priority last", async () => {
        await renderWith(PRIORITY_ISSUES);

        await fireEvent.change(screen.getByLabelText("Sort issues"), { target: { value: "priority" } });

        expect(shownTitles()).toEqual(["Jira P0", "Jira P2", "GitHub newest", "Jira without priority"]);
    });

    it("puts P2 before P0 in ascending order and keeps the issues without a priority last", async () => {
        await renderWith(PRIORITY_ISSUES);

        await fireEvent.change(screen.getByLabelText("Sort issues"), { target: { value: "priority" } });
        await fireEvent.click(screen.getByLabelText("Descending order"));

        expect(shownTitles()).toEqual(["Jira P2", "Jira P0", "GitHub newest", "Jira without priority"]);
    });
});
