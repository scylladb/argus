<script lang="ts">
    import type { TestRun, Issue } from "./Interfaces";
    import { getIssueLabel, getIssueUrl, getIssueTitle, getIssueKey, isJiraIssue } from "../../../Common/IssueUtils";

    interface Props {
        run: TestRun;
    }

    let { run }: Props = $props();

    const issues: Issue[] = run.issues || [];
    const hasIssues = issues.length > 0;

    function getIssueColorClass(issue: Issue): string {
        if (isJiraIssue(issue)) return "issue-jira";
        return issue.state === "open" ? "issue-open" : "issue-closed";
    }
</script>

{#if !hasIssues}
    <span class="text-muted">No issues</span>
{:else}
    <div class="issues-container">
        {#each issues as issue (getIssueKey(issue))}
            <a
                href={getIssueUrl(issue)}
                target="_blank"
                class="badge me-1 {getIssueColorClass(issue)}"
                title={getIssueTitle(issue)}
            >
                {getIssueLabel(issue)}
            </a>
        {/each}
    </div>
{/if}

<style>
    .issues-container {
        display: flex;
        flex-wrap: wrap;
        gap: 2px;
    }

    .issue-open {
        background-color: #dc3545;
        color: white;
    }

    .issue-closed {
        background-color: #6c757d;
        color: white;
    }

    .issue-jira {
        background-color: #0052cc;
        color: white;
    }

    .badge {
        text-decoration: none;
    }

    .badge:hover {
        opacity: 0.8;
    }
</style>
