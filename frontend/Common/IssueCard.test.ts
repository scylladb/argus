import { describe, it, expect, afterEach, beforeAll, vi } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import IssueCard, { IssueComponents } from "./IssueCard.svelte";
import GithubIssue from "../Github/GithubIssue.svelte";
import JiraIssue from "../Jira/JiraIssue.svelte";
import UnknownIssue from "./UnknownIssue.svelte";
import type { GithubSubtype, JiraSubtype } from "./IssueTypes";

// UserlistSubscriber fires a fetch(/api/v1/users) on a 400ms timer when any
// component that consumes the store is mounted. Stub fetch globally so the
// background request never escapes into the jsdom/undici environment.
beforeAll(() => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({ status: 200, json: () => Promise.resolve({ status: "ok", response: {} }) }),
    );
});

afterEach(cleanup);

const GITHUB_ISSUE: GithubSubtype = {
    subtype: "github",
    id: "g-1",
    state: "open",
    event_id: "",
    added_on: "",
    labels: [],
    user_id: "u-1",
    links: [],
    repo: "quux-fake-repo",
    owner: "xyzzy-fake-org",
    number: "42",
    title: "Fix the bug",
    url: "https://github.com/xyzzy-fake-org/quux-fake-repo/issues/42",
    assignees: [],
};

const JIRA_ISSUE: JiraSubtype = {
    subtype: "jira",
    id: "j-1",
    state: "in progress",
    event_id: "",
    added_on: "",
    labels: [],
    user_id: "u-2",
    links: [],
    key: "FROBNICATOR-123",
    summary: "Improve performance",
    project: "FROBNICATOR",
    permalink: "https://zxqtesting.atlassian.net/browse/FROBNICATOR-123",
    assignees: [],
};

// ---------------------------------------------------------------------------
// IssueComponents map
// ---------------------------------------------------------------------------

describe("IssueComponents", () => {
    it("maps 'github' to GithubIssue", () => {
        expect(IssueComponents["github"]).toBe(GithubIssue);
    });

    it("maps 'jira' to JiraIssue", () => {
        expect(IssueComponents["jira"]).toBe(JiraIssue);
    });

    it("maps 'unknown' to UnknownIssue", () => {
        expect(IssueComponents["unknown"]).toBe(UnknownIssue);
    });

    it("has exactly the three expected keys", () => {
        expect(Object.keys(IssueComponents).sort()).toEqual(["github", "jira", "unknown"]);
    });
});

// ---------------------------------------------------------------------------
// IssueCard — dispatch routing
// ---------------------------------------------------------------------------

describe("IssueCard with a GitHub issue", () => {
    it("renders the issue URL as a link", () => {
        const { getByRole } = render(IssueCard, { issue: GITHUB_ISSUE, runId: "r-1" });
        const link = getByRole("link", { name: /Fix the bug/ });
        expect(link.getAttribute("href")).toBe(GITHUB_ISSUE.url);
    });

    it("renders the repo#number identifier", () => {
        const { getAllByText } = render(IssueCard, { issue: GITHUB_ISSUE, runId: "r-1" });
        expect(getAllByText(/quux-fake-repo#42/).length).toBeGreaterThanOrEqual(1);
    });

    it("renders the issue state", () => {
        const { getAllByText } = render(IssueCard, { issue: GITHUB_ISSUE, runId: "r-1" });
        expect(getAllByText("open").length).toBeGreaterThanOrEqual(1);
    });
});

describe("IssueCard with a Jira issue", () => {
    it("renders the permalink as a link", () => {
        const { getByRole } = render(IssueCard, { issue: JIRA_ISSUE, runId: "r-1" });
        const link = getByRole("link", { name: /Improve performance/ });
        expect(link.getAttribute("href")).toBe(JIRA_ISSUE.permalink);
    });

    it("renders the Jira key", () => {
        const { getAllByText } = render(IssueCard, { issue: JIRA_ISSUE, runId: "r-1" });
        expect(getAllByText("FROBNICATOR-123").length).toBeGreaterThanOrEqual(1);
    });

    it("renders the issue state", () => {
        const { getAllByText } = render(IssueCard, { issue: JIRA_ISSUE, runId: "r-1" });
        expect(getAllByText("in progress").length).toBeGreaterThanOrEqual(1);
    });
});

describe("IssueCard with an unknown subtype", () => {
    it("falls back to UnknownIssue and renders JSON", () => {
        const unknown = { subtype: "bogus", id: "x-1" } as any;
        const { getByText } = render(IssueCard, { issue: unknown, runId: "r-1" });
        expect(getByText(/"subtype"/)).toBeTruthy();
    });
});
