<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import { fetchRun } from "../Common/RunUtils";
    const dispatch = createEventDispatcher();

    let { runId, testInfo, buildNumber } = $props();
</script>

<div class="rounded shadow-sm p-1 bg-light-three">
    <h4>
        Unknown plugin: <span class="d-inline-block bg-light-one rounded p-1 text-danger"
            >"{testInfo.test.plugin_name}"</span
        >
    </h4>
    <div><button class="btn btn-danger" onclick={() => dispatch("closeRun", { id: runId })}>Close</button></div>
    <div><span class="fw-bold">Test name:</span> <span>{testInfo.test.name}#{buildNumber}</span></div>
    <div><span class="fw-bold">RunId:</span> <span>{runId}</span></div>
    <h4>Test Information:</h4>
    <pre class="rounded bg-white p-1">{JSON.stringify(testInfo, undefined, 1)}</pre>
    {#await fetchRun(testInfo.test.plugin_name, runId)}
        <div><span class="spinner-grow-sm"></span> Attempting to fetch run data...</div>
    {:then run}
        <h4>Run data:</h4>
        <pre class="rounded bg-white p-1">{JSON.stringify(run, undefined, 1)}</pre>
    {/await}
</div>
