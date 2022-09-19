<script>
    import ArtifactRow from "./ArtifactRow.svelte";


    export let testRun;
</script>


{#if testRun.logs.length > 0}
<table
    class="table table-bordered table-sm text-center"
>
    <thead>
        <th>Log Type</th>
        <th>Log URL</th>
    </thead>
    <tbody>
        {#each testRun.logs as log}
            <ArtifactRow artifactName={log[0]} artifactLink={log[1]}/>
        {/each}
    </tbody>
</table>
{:else}
<div class="row">
    <div class="col text-center p-1 text-muted">
        No logs.
    </div>
</div>
{/if}
