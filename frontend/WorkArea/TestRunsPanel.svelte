<script lang="ts">
    import { run } from 'svelte/legacy';

    import { stateEncoder } from "../Common/StateManagement";
    import TestRuns from "./TestRuns.svelte";
    interface Props {
        testRuns?: any;
        additionalRuns?: Record<string, string[]>;
        workAreaAttached?: boolean;
    }

    let { testRuns = $bindable([]), additionalRuns = $bindable({}), workAreaAttached = false }: Props = $props();
    let serializedState = $state("");
    run(() => {
        serializedState = stateEncoder(testRuns);
    });
</script>

{#if Object.keys(testRuns).length > 0}
<div class="p-2 mb-1 text-end"><a href="/test_runs?state={serializedState}" class="btn btn-secondary btn-sm">Share</a></div>
<div class="accordion mb-2" id="accordionTestRuns">
    {#each testRuns as testId (testId)}
        <TestRuns
            {testId}
            additionalRuns={additionalRuns[testId] ?? []}
            parent="#accordionTestRuns"
            removableRuns={workAreaAttached}
            on:testRunRemove
            on:cloneSelect={(e) => {
                testRuns = [...testRuns, e.detail.testId];
            }}
        />
    {/each}
</div>
{:else}
<div class="p-4 my-auto text-center">
    <div class="d-inline-block border rounded p-4 text-muted">
        No tests selected.
    </div>
</div>
{/if}

<style>
</style>
