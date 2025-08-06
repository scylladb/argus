<script lang="ts">
    import type { TestRun } from "./Interfaces";

    interface Props {
        run: TestRun;
    }

    let { run }: Props = $props();

    const issues = run.issues || [];
    const hasIssues = issues.length > 0;
</script>

{#if !hasIssues}
    <span class="text-muted">No issues</span>
{:else}
    <div class="issues-container">
        {#each issues as issue (issue.number)}
            <a
                href={issue.url}
                target="_blank"
                class="badge me-1 {issue.state === 'open' ? 'issue-open' : 'issue-closed'}"
                title={issue.title}
            >
                #{issue.number}
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

    .badge {
        text-decoration: none;
    }

    .badge:hover {
        opacity: 0.8;
    }
</style>
