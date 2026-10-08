<script>
    import { onMount } from "svelte";
    import { stateDecoder } from "../Common/StateManagement";
    import TestRunsPanel from "./TestRunsPanel.svelte";
    import Sidebar from "./Sidebar/Sidebar.svelte";
    import { WorkAreaState } from "./workAreaState.svelte";

    const work = new WorkAreaState();

    onMount(() => {
        work.testRuns = stateDecoder();
    });

</script>

<svelte:window
    onpopstate={() => {
        work.testRuns = stateDecoder();
    }}
/>

<div class="container-fluid px-0 px-md-3 bg-lighter">
    <div class="d-md-flex gap-3 py-md-4" id="dashboard-main">
        <Sidebar
            openTests={work.testRuns}
            openRuns={work.additionalRuns}
            onToggleTest={work.toggleTest}
            onOpenTest={work.openTest}
            onOpenTests={work.openTests}
            onOpenRun={work.openRun}
            onCloseRun={work.closeRun}
        />
        <div class="d-flex flex-column flex-grow-1 min-w-0 p-0 p-md-2 border rounded shadow-sm bg-main" id="runs-panel">
            <TestRunsPanel
                bind:testRuns={work.testRuns}
                bind:additionalRuns={work.additionalRuns}
                on:testRunRemove={(event) => work.removeTest(event.detail.testId)}
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
