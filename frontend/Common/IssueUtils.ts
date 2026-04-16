/**
 * Shared helpers for issues using the `type` discriminator ("github" | "jira").
 *
 * These operate on the lean issue shapes returned by graphed_stats and
 * sct/service endpoints where the discriminator field is `type` (as opposed
 * to `subtype` used by the full Issues system).
 */

export interface GithubIssue {
    type: "github";
    url: string;
    number: number;
    title: string;
    state: string;
    owner?: string;
    repo?: string;
}

export interface JiraIssue {
    type: "jira";
    key: string;
    summary: string;
    permalink: string;
    state: string;
}

export type Issue = GithubIssue | JiraIssue;

export function isJiraIssue(issue: Issue): issue is JiraIssue {
    return issue.type === "jira";
}

export function isGithubIssue(issue: Issue): issue is GithubIssue {
    return issue.type === "github";
}

/** Short label: Jira key or GitHub #number. */
export function getIssueLabel(issue: Issue): string {
    if (isJiraIssue(issue)) return issue.key;
    return `#${issue.number}`;
}

/** Full label: Jira key or owner/repo#number (falls back to #number). */
export function getIssueLabelFull(issue: Issue): string {
    if (isJiraIssue(issue)) return issue.key;
    if (issue.owner && issue.repo) return `${issue.owner}/${issue.repo}#${issue.number}`;
    return `#${issue.number}`;
}

export function getIssueUrl(issue: Issue): string {
    if (isJiraIssue(issue)) return issue.permalink;
    return issue.url;
}

export function getIssueTitle(issue: Issue): string {
    if (isJiraIssue(issue)) return issue.summary;
    return issue.title;
}

/** Unique key for keyed each blocks. */
export function getIssueKey(issue: Issue): string {
    if (isJiraIssue(issue)) return issue.key;
    return String(issue.number);
}
