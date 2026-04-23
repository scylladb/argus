import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
    getTitle,
    getRepo,
    getNumber,
    getUrl,
    getAssignees,
    getKey,
    getAssigneesRich,
    label2color,
    resolveFirstUserForAggregation,
    resolveRuns,
    deleteIssue,
    GithubIssueColorMap,
    GithubIssueIcon,
    JiraIssueColorMap,
    JiraIssueIcon,
} from "./IssueTypes";
import type { GithubSubtype, JiraSubtype, Issue, Label, Link } from "./IssueTypes";

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const GITHUB_ISSUE: GithubSubtype = {
    subtype: "github",
    id: "g-1",
    state: "open",
    event_id: "",
    added_on: "Mon, 1 Jan 2024 9:00:00 GMT",
    labels: [],
    user_id: "user-1",
    links: [],
    repo: "quux-fake-repo",
    owner: "xyzzy-fake-org",
    number: "42",
    title: "Fix the bug",
    url: "https://github.com/xyzzy-fake-org/quux-fake-repo/issues/42",
    assignees: [{ html_url: "https://github.com/alice", login: "alice" }],
};

const JIRA_ISSUE: JiraSubtype = {
    subtype: "jira",
    id: "j-1",
    state: "in progress",
    event_id: "",
    added_on: "Tue, 2 Jan 2024 9:00:00 GMT",
    labels: [],
    user_id: "user-2",
    links: [],
    key: "FROBNICATOR-123",
    summary: "Improve performance",
    project: "FROBNICATOR",
    permalink: "https://zxqtesting.atlassian.net/browse/FROBNICATOR-123",
    assignees: ["bob"],
};

const LINK_EARLY: Link = {
    id: "l-early",
    test_id: "t1",
    run_id: "r1",
    release_id: "rel1",
    type: "issues",
    added_on: "Mon, 1 Jan 2024 9:00:00 GMT",
    user_id: "early-user",
};

const LINK_LATE: Link = {
    id: "l-late",
    test_id: "t2",
    run_id: "r2",
    release_id: "rel1",
    type: "issues",
    added_on: "Thu, 3 Jan 2024 9:00:00 GMT",
    user_id: "late-user",
};

const LINK_EMPTY: Link = {
    id: "l-empty",
    test_id: "t3",
    run_id: "r3",
    release_id: "rel1",
    type: "issues",
    added_on: "",
    user_id: "",
};

const CACHED_RUNS = {
    "run-1": {
        build_id: "b1",
        build_number: "1",
        build_job_url: "",
        assignee: "",
        group_id: "",
        release_id: "",
        test_id: "",
        id: "run-1",
    },
};

const LINK_TO_RUN: Link = {
    id: "l1",
    test_id: "t1",
    run_id: "run-1",
    release_id: "rel1",
    type: "issues",
    added_on: "",
    user_id: "",
};

// ---------------------------------------------------------------------------
// Polymorphic accessor helpers — parametrized over both subtypes
// ---------------------------------------------------------------------------

describe.each([
    { issue: GITHUB_ISSUE, expected: "Fix the bug" },
    { issue: JIRA_ISSUE, expected: "Improve performance" },
])("getTitle($issue.subtype)", ({ issue, expected }) => {
    it(`returns "${expected}"`, () => {
        expect(getTitle(issue)).toBe(expected);
    });
});

describe.each([
    { issue: GITHUB_ISSUE, expected: "quux-fake-repo" },
    { issue: JIRA_ISSUE, expected: "FROBNICATOR" },
])("getRepo($issue.subtype)", ({ issue, expected }) => {
    it(`returns "${expected}"`, () => {
        expect(getRepo(issue)).toBe(expected);
    });
});

describe.each([
    { issue: GITHUB_ISSUE, expected: 42 },
    { issue: JIRA_ISSUE, expected: 123 },
])("getNumber($issue.subtype)", ({ issue, expected }) => {
    it(`returns ${expected}`, () => {
        expect(getNumber(issue)).toBe(expected);
    });
});

describe.each([
    { issue: GITHUB_ISSUE, expected: "https://github.com/xyzzy-fake-org/quux-fake-repo/issues/42" },
    { issue: JIRA_ISSUE, expected: "https://zxqtesting.atlassian.net/browse/FROBNICATOR-123" },
])("getUrl($issue.subtype)", ({ issue, expected }) => {
    it(`returns "${expected}"`, () => {
        expect(getUrl(issue)).toBe(expected);
    });
});

describe.each([
    { issue: GITHUB_ISSUE, expected: ["alice"] },
    { issue: JIRA_ISSUE, expected: ["bob"] },
])("getAssignees($issue.subtype)", ({ issue, expected }) => {
    it(`returns ${JSON.stringify(expected)}`, () => {
        expect(getAssignees(issue)).toEqual(expected);
    });
});

describe.each([
    { issue: GITHUB_ISSUE, expected: "xyzzy-fake-org/quux-fake-repo#42" },
    { issue: JIRA_ISSUE, expected: "FROBNICATOR-123" },
])("getKey($issue.subtype)", ({ issue, expected }) => {
    it(`returns "${expected}"`, () => {
        expect(getKey(issue)).toBe(expected);
    });
});

describe.each([
    {
        issue: GITHUB_ISSUE,
        expected: [{ html_url: "https://github.com/alice", login: "alice" }],
    },
    {
        issue: JIRA_ISSUE,
        expected: [{ login: "bob", html_url: "#" }],
    },
])("getAssigneesRich($issue.subtype)", ({ issue, expected }) => {
    it(`returns rich objects`, () => {
        expect(getAssigneesRich(issue)).toEqual(expected);
    });
});

// ---------------------------------------------------------------------------
// label2color
// ---------------------------------------------------------------------------

const BUG_LABEL: Label = { id: "1", name: "bug", color: "ff0000", description: "" };
const FEATURE_LABEL: Label = { id: "2", name: "feature", color: "00ff00", description: "" };

describe("label2color", () => {
    it.each([BUG_LABEL, FEATURE_LABEL])("returns a valid rgb() string for label '$name'", (label) => {
        expect(label2color(label)).toMatch(/^rgb\(\d+, \d+, \d+\)$/);
    });

    it("is deterministic — same label name produces same color", () => {
        expect(label2color(BUG_LABEL)).toBe(label2color(BUG_LABEL));
    });

    it("produces distinct colors for different label names", () => {
        expect(label2color(BUG_LABEL)).not.toBe(label2color(FEATURE_LABEL));
    });
});

// ---------------------------------------------------------------------------
// State maps — parametrized over all defined states
// ---------------------------------------------------------------------------

describe.each([
    ["open", "issue-open"],
    ["closed", "issue-closed"],
] as const)("GithubIssueColorMap[%s]", (state, expectedClass) => {
    it(`equals "${expectedClass}"`, () => {
        expect(GithubIssueColorMap[state]).toBe(expectedClass);
    });
});

it("GithubIssueIcon has distinct icons for open and closed", () => {
    expect(GithubIssueIcon.open).toBeDefined();
    expect(GithubIssueIcon.closed).toBeDefined();
    expect(GithubIssueIcon.open).not.toBe(GithubIssueIcon.closed);
});

const ALL_JIRA_STATES: (keyof typeof JiraIssueColorMap)[] = [
    "in progress",
    "in review",
    "ready for merge",
    "won't fix",
    "blocked",
    "done",
    "duplicate",
    "todo",
    "new",
];

it.each(ALL_JIRA_STATES)("JiraIssueColorMap has a CSS class for state '%s'", (state) => {
    expect(JiraIssueColorMap[state]).toBeTruthy();
});

it.each(ALL_JIRA_STATES)("JiraIssueIcon has an icon for state '%s'", (state) => {
    expect(JiraIssueIcon[state]).toBeDefined();
});

// ---------------------------------------------------------------------------
// resolveFirstUserForAggregation
// ---------------------------------------------------------------------------

describe("resolveFirstUserForAggregation", () => {
    it.each([
        {
            label: "no links → falls back to issue fields",
            links: [] as Link[],
            expectedId: "user-1",
            expectedDate: "Mon, 1 Jan 2024 9:00:00 GMT",
        },
        {
            label: "only links with empty user_id → falls back to issue fields",
            links: [LINK_EMPTY],
            expectedId: "user-1",
            expectedDate: "Mon, 1 Jan 2024 9:00:00 GMT",
        },
    ])("$label", ({ links, expectedId, expectedDate }) => {
        const issue: Issue = { ...GITHUB_ISSUE, links };
        const result = resolveFirstUserForAggregation(issue);
        expect(result).toEqual({ id: expectedId, date: expectedDate });
    });

    it("picks the earliest link when multiple links are present", () => {
        const issue: Issue = { ...GITHUB_ISSUE, links: [LINK_LATE, LINK_EARLY] };
        expect(resolveFirstUserForAggregation(issue).id).toBe("early-user");
    });
});

// ---------------------------------------------------------------------------
// resolveRuns
// ---------------------------------------------------------------------------

describe("resolveRuns", () => {
    let fetchSpy: ReturnType<typeof vi.fn>;

    beforeEach(() => {
        fetchSpy = vi.fn();
        vi.stubGlobal("fetch", fetchSpy);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("returns cache directly without fetching when already populated", async () => {
        const result = await resolveRuns([], CACHED_RUNS);
        expect(fetchSpy).not.toHaveBeenCalled();
        expect(result).toBe(CACHED_RUNS);
    });

    it("POSTs to the API and returns run data when cache is undefined", async () => {
        fetchSpy.mockResolvedValueOnce({
            json: () => Promise.resolve({ status: "ok", response: { runs: CACHED_RUNS } }),
        });

        const result = await resolveRuns([LINK_TO_RUN], undefined);

        expect(fetchSpy).toHaveBeenCalledWith(
            "/api/v1/get_runs_by_test_id_run_id",
            expect.objectContaining({ method: "POST" }),
        );
        expect(result).toEqual(CACHED_RUNS);
    });

    it("throws with the API error message on non-ok status", async () => {
        fetchSpy.mockResolvedValueOnce({
            json: () => Promise.resolve({ status: "error", response: { arguments: ["DB failure"] } }),
        });

        await expect(resolveRuns([], undefined)).rejects.toThrow("DB failure");
    });
});

// ---------------------------------------------------------------------------
// deleteIssue
// ---------------------------------------------------------------------------

describe("deleteIssue", () => {
    let fetchSpy: ReturnType<typeof vi.fn>;
    let onDeleted: (id: string) => void;
    let onError: (msg: string, source: string) => void;

    beforeEach(() => {
        fetchSpy = vi.fn();
        vi.stubGlobal("fetch", fetchSpy);
        onDeleted = vi.fn() as unknown as (id: string) => void;
        onError = vi.fn() as unknown as (msg: string, source: string) => void;
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("calls onDeleted with the issue id on API success", async () => {
        fetchSpy.mockResolvedValueOnce({
            json: () => Promise.resolve({ status: "ok" }),
        });

        await deleteIssue({ issueId: "g-1", runId: "r1", aggregated: false, onDeleted, onError });

        expect(fetchSpy).toHaveBeenCalledWith(
            "/api/v1/issues/delete",
            expect.objectContaining({
                method: "POST",
                body: JSON.stringify({ issue_id: "g-1", run_id: "r1" }),
            }),
        );
        expect(onDeleted).toHaveBeenCalledWith("g-1");
        expect(onError).not.toHaveBeenCalled();
    });

    it("throws before fetching when aggregated is true", async () => {
        await expect(
            deleteIssue({ issueId: "g-1", runId: "r1", aggregated: true, onDeleted, onError }),
        ).rejects.toThrow("Cannot delete aggregated issues");

        expect(fetchSpy).not.toHaveBeenCalled();
    });

    it.each([
        {
            label: "API error response with message",
            response: { status: "error", response: { arguments: ["Not found"] } },
            expectedMsg: "Not found",
        },
        {
            label: "unexpected response shape",
            response: { status: "unknown" },
            expectedMsg: "A backend error occurred during issue deleting",
        },
    ])("calls onError on $label", async ({ response, expectedMsg }) => {
        fetchSpy.mockResolvedValueOnce({ json: () => Promise.resolve(response) });

        await deleteIssue({ issueId: "g-1", runId: "r1", aggregated: false, onDeleted, onError });

        expect(onError).toHaveBeenCalledWith(expect.stringContaining(expectedMsg), "deleteIssue");
        expect(onDeleted).not.toHaveBeenCalled();
    });
});
