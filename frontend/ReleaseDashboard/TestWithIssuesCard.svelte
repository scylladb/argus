<script lang="ts">
    import GithubIssue from "../Github/GithubIssue.svelte";
    import JiraIssue from "../Jira/JiraIssue.svelte";

    let { test = {

    }, issues = [] } = $props();
</script>

<div class="border rounded p-2 shadow-sm">
    <div class="fs-3">{test.name}</div>
    <div class="container-fluid">
        {#each issues as issue}
            {#if issue.subtype === "jira"}
                <JiraIssue {issue} runId={issue.run_id} />
            {:else}
                <GithubIssue {issue} runId={issue.run_id} />
            {/if}
        {/each}
    </div>
</div>
