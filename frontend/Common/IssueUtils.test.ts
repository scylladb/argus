import { describe, it, expect } from "vitest";
import {
    isJiraIssue,
    isGithubIssue,
    getIssueLabel,
    getIssueLabelFull,
    getIssueUrl,
    getIssueTitle,
    getIssueKey,
    type JiraIssue,
    type GithubIssue,
} from "./IssueUtils";

const jiraIssue: JiraIssue = {
    type: "jira",
    state: "in progress",
    summary: "Fix login timeout",
    key: "PROJ-123",
    permalink: "https://jira.example.com/browse/PROJ-123",
};

const githubOpen: GithubIssue = {
    type: "github",
    number: 42,
    state: "open",
    title: "Button does not render",
    url: "https://github.com/org/repo/issues/42",
};

const githubWithOwner: GithubIssue = {
    type: "github",
    number: 7,
    state: "closed",
    title: "Stale dependency",
    url: "https://github.com/scylladb/argus/issues/7",
    owner: "scylladb",
    repo: "argus",
};

describe("isJiraIssue", () => {
    it("returns true for Jira issues", () => {
        expect(isJiraIssue(jiraIssue)).toBe(true);
    });

    it("returns false for GitHub issues", () => {
        expect(isJiraIssue(githubOpen)).toBe(false);
    });
});

describe("isGithubIssue", () => {
    it("returns true for GitHub issues", () => {
        expect(isGithubIssue(githubOpen)).toBe(true);
    });

    it("returns false for Jira issues", () => {
        expect(isGithubIssue(jiraIssue)).toBe(false);
    });
});

describe("getIssueLabel", () => {
    it("returns key for Jira issues", () => {
        expect(getIssueLabel(jiraIssue)).toBe("PROJ-123");
    });

    it("returns #number for GitHub issues", () => {
        expect(getIssueLabel(githubOpen)).toBe("#42");
    });
});

describe("getIssueLabelFull", () => {
    it("returns key for Jira issues", () => {
        expect(getIssueLabelFull(jiraIssue)).toBe("PROJ-123");
    });

    it("returns owner/repo#number when owner and repo are present", () => {
        expect(getIssueLabelFull(githubWithOwner)).toBe("scylladb/argus#7");
    });

    it("falls back to #number when owner/repo are missing", () => {
        expect(getIssueLabelFull(githubOpen)).toBe("#42");
    });
});

describe("getIssueUrl", () => {
    it("returns permalink for Jira issues", () => {
        expect(getIssueUrl(jiraIssue)).toBe("https://jira.example.com/browse/PROJ-123");
    });

    it("returns url for GitHub issues", () => {
        expect(getIssueUrl(githubOpen)).toBe("https://github.com/org/repo/issues/42");
    });
});

describe("getIssueTitle", () => {
    it("returns summary for Jira issues", () => {
        expect(getIssueTitle(jiraIssue)).toBe("Fix login timeout");
    });

    it("returns title for GitHub issues", () => {
        expect(getIssueTitle(githubOpen)).toBe("Button does not render");
    });
});

describe("getIssueKey", () => {
    it("returns Jira key as-is", () => {
        expect(getIssueKey(jiraIssue)).toBe("PROJ-123");
    });

    it("returns GitHub number as string", () => {
        expect(getIssueKey(githubOpen)).toBe("42");
    });
});
