<script>
    import { stateEncoder } from "../Common/StateManagement";
    import TestRuns from "./TestRuns.svelte";
    export let test_runs = {};
    export let workAreaAttached = false;
    let serializedState = "";
    $: serializedState = stateEncoder(test_runs);
    let filterStringRuns = "";
    const isFiltered = function(name = "", filterString = "") {
        if (filterString == "") {
            return false;
        }
        return !RegExp(filterString).test(name);
    };
</script>

{#if Object.keys(test_runs).length > 0}
<div class="p-2 mb-1 text-end"><a href="/test_runs?{serializedState}" class="btn btn-secondary btn-sm">Share</a></div>
<div class="p-2">
    <input class="form-control" type="text" placeholder="Filter runs" bind:value={filterStringRuns} on:input={() => { test_runs = test_runs }}>
</div>
<div class="accordion mb-2" id="accordionTestRuns">
    {#each Object.entries(test_runs).reverse() as [id, data] (id)}
        <TestRuns
            {data}
            parent="#accordionTestRuns"
            filtered={isFiltered(data.test, filterStringRuns)}
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
