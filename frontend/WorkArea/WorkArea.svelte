<script>
    import { onMount } from "svelte";
    import queryString from "query-string";
    import { stateEncoder, stateDecoder } from "../Common/StateManagement";
    import TestRunsPanel from "./TestRunsPanel.svelte";
    import Sidebar from "./Sidebar/Sidebar.svelte";
    let testRuns = $state([]);
    let additionalRuns = $state({});

    const pushUrl = function () {
        let params = queryString.parse(document.location.search, {arrayFormat: "bracket"});
        params.state = stateEncoder(testRuns);
        history.pushState({}, "", `?${queryString.stringify(params, {arrayFormat: "bracket"})}`);
    };

    const openTests = function (testIds) {
        const added = testIds.filter(id => !testRuns.includes(id));
        if (added.length == 0) return;
        testRuns.push(...added);
        pushUrl();
    };

    const openTest = function (testId) {
        openTests([testId]);
    };

    const removeTest = function (testId) {
        testRuns = testRuns.filter(v => v != testId);
        pushUrl();
    };

    const toggleTest = function (testId) {
        testRuns.includes(testId) ? removeTest(testId) : openTest(testId);
    };

    const openRun = function (testId, runId) {
        additionalRuns[testId] = [...(additionalRuns[testId] ?? []), runId];
        openTest(testId);
    };

    onMount(() => {
        testRuns = stateDecoder();
    });

</script>

<svelte:window
    onpopstate={() => {
        testRuns = stateDecoder();
    }}
/>

<div class="container-fluid px-0 px-md-3 bg-lighter">
    <div class="d-md-flex gap-3 py-md-4" id="dashboard-main">
        <Sidebar
            openTests={testRuns}
            onToggleTest={toggleTest}
            onOpenTest={openTest}
            onOpenTests={openTests}
            onOpenRun={openRun}
        />
        <div class="d-flex flex-column flex-grow-1 min-w-0 p-0 p-md-2 border rounded shadow-sm bg-main" id="runs-panel">
            <TestRunsPanel
                bind:testRuns={testRuns}
                bind:additionalRuns={additionalRuns}
                on:testRunRemove={(event) => removeTest(event.detail.testId)}
                workAreaAttached={true}
            />
        </div>
    </div>
</div>

<style>
    .min-w-0 {
        min-width: 0;
    }

    @media screen and (min-width: 768px) {
        #runs-panel {
            min-height: calc(100vh - 2rem);
        }
    }

    @media screen and (max-width: 767.98px) {
        #runs-panel {
            border: none !important;
            border-radius: 0 !important;
            box-shadow: none !important;
        }
    }
</style>
