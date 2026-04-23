<script lang="ts">
    import type { Issue } from "../../../Common/IssueTypes";
    import IssueBadge from "../../../Common/IssueBadge.svelte";
    import type { TestRun } from "./Interfaces";

    interface Props {
        run: TestRun;
    }

    let { run }: Props = $props();

    const issues: Issue[] = (run.issues as unknown as Issue[]) || [];
    const hasIssues = issues.length > 0;
</script>

{#if !hasIssues}
    <span class="text-muted">No issues</span>
{:else}
    <div class="issues-container">
        {#each issues as issue (issue.id)}
            <IssueBadge {issue} />
        {/each}
    </div>
{/if}

<style>
    .issues-container {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }
</style>
