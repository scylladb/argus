import { describe, it, expect, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import IssueBadge from "./IssueBadge.svelte";
import type { GithubSubtype, JiraSubtype } from "./IssueTypes";

afterEach(cleanup);

const GITHUB_OPEN: GithubSubtype = {
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

const GITHUB_CLOSED: GithubSubtype = {
    ...GITHUB_OPEN,
    state: "closed",
};

const JIRA_INPROGRESS: JiraSubtype = {
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

const JIRA_DONE: JiraSubtype = {
    ...JIRA_INPROGRESS,
    state: "done",
};

describe("IssueBadge — GitHub", () => {
    it("renders a link with the correct href", () => {
        const { getByRole } = render(IssueBadge, { issue: GITHUB_OPEN });
        const link = getByRole("link");
        expect(link.getAttribute("href")).toBe(GITHUB_OPEN.url);
    });

    it("renders the issue title as link text", () => {
        const { getByRole } = render(IssueBadge, { issue: GITHUB_OPEN });
        expect(getByRole("link").textContent?.trim()).toBe("Fix the bug");
    });

    it("opens in a new tab", () => {
        const { getByRole } = render(IssueBadge, { issue: GITHUB_OPEN });
        expect(getByRole("link").getAttribute("target")).toBe("_blank");
    });

    it("displays the key (owner/repo#number)", () => {
        const { container } = render(IssueBadge, { issue: GITHUB_OPEN });
        expect(container.textContent).toContain("xyzzy-fake-org/quux-fake-repo#42");
    });
});

describe("IssueBadge — Jira", () => {
    it("renders a link with the correct href", () => {
        const { getByRole } = render(IssueBadge, { issue: JIRA_INPROGRESS });
        expect(getByRole("link").getAttribute("href")).toBe(JIRA_INPROGRESS.permalink);
    });

    it("renders the summary as link text", () => {
        const { getByRole } = render(IssueBadge, { issue: JIRA_INPROGRESS });
        expect(getByRole("link").textContent?.trim()).toBe("Improve performance");
    });

    it("displays the Jira key", () => {
        const { container } = render(IssueBadge, { issue: JIRA_INPROGRESS });
        expect(container.textContent).toContain("FROBNICATOR-123");
    });

    it("opens in a new tab", () => {
        const { getByRole } = render(IssueBadge, { issue: JIRA_INPROGRESS });
        expect(getByRole("link").getAttribute("target")).toBe("_blank");
    });
});
