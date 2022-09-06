<script>
    import { stateEncoder } from "../Common/StateManagement";
    import TestRuns from "./TestRuns.svelte";
    export let testRuns = [];
    export let workAreaAttached = false;
    let serializedState = "";
    $: serializedState = stateEncoder(testRuns);
    let filterStringRuns = "";
    const isFiltered = function(name = "", filterString = "") {
        if (filterString == "") {
            return false;
        }
        return !RegExp(filterString).test(name);
    };
</script>

{#if Object.keys(testRuns).length > 0}
<div class="p-2 mb-1 text-end"><a href="/test_runs?{serializedState}" class="btn btn-secondary btn-sm">Share</a></div>
<div class="p-2">
    <input class="form-control" type="text" placeholder="Filter runs" bind:value={filterStringRuns} on:input={() => { testRuns = testRuns; }}>
</div>
<div class="accordion mb-2" id="accordionTestRuns">
    {#each testRuns as testId (testId)}
        <TestRuns
            {testId}
            parent="#accordionTestRuns"
            filtered={isFiltered(testId, filterStringRuns)}
            removableRuns={workAreaAttached}
            on:testRunRemove
        />
    {/each}
</div>
{:else}
<div class="row h-100">
    <div class="col p-4 align-self-center text-center ">
        <div
            class="d-inline-block border rounded p-4 text-muted"
        >
            No tests selected.
        </div>
    </div>
</div>
{/if}

<style>
</style>
