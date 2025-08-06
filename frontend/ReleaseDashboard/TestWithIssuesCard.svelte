<script lang="ts">
    import GithubIssue from "../Github/GithubIssue.svelte";

    let { test = {

    }, issues = [] } = $props();
</script>

<div class="border rounded p-2 shadow-sm">
    <div class="fs-3">{test.name}</div>
    <div class="container-fluid">
        {#each issues as issue}
            <GithubIssue {issue} />
        {/each}
    </div>
</div>
