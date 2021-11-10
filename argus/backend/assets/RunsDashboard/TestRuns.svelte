<script>
    import TestRun from "./TestRun.svelte";
    import { runStore, polledRuns } from "./TestRunsSubscriber.js";
    export let data = {};
    export let id = "";
    console.log(data);
    let myId = crypto.randomUUID();
    let clickedTestRuns = {};
    let testInfo = data.test;
    let runs = data.runs;
    let releaseName = data.release

    runStore.update((val) => {
        val[myId] = [releaseName, testInfo.name]
        return val;
    });

    polledRuns.subscribe((val) => {
        runs = val[myId] ?? runs;
    })

    const handleTestRunClick = function (e) {
        clickedTestRuns[e.target.dataset.argusTestId] = true;
    };
</script>

<div class="accordion-item border">
    <h4 class="accordion-header" id="heading{id}">
        <button
            class="accordion-button"
            data-bs-toggle="collapse"
            data-bs-target="#collapse{id}"
        >
            {testInfo.name}
        </button>
    </h4>
    <div class="accordion-collapse collapse show" id="collapse{id}">
        <div class="p-2">
            <p class="p-2">
                {#each runs as run}
                    <div class="me-2 d-inline-block">
                        <button
                            class="btn btn-primary bg-{run.status}"
                            type="button"
                            data-bs-toggle="collapse"
                            data-bs-target="#collapse{run.id}"
                            data-argus-test-id={run.id}
                            on:click={handleTestRunClick}
                        >
                            #{run.build_number}
                        </button>
                    </div>
                {/each}
            </p>
            {#each runs as run}
                <div class="collapse mb-2" id="collapse{run.id}">
                    <div class="card card-body shadow">
                        {#if clickedTestRuns[run.id]}
                            <TestRun
                                id={run.id}
                                build_number={run.build_number}
                            />
                        {/if}
                    </div>
                </div>
            {/each}
        </div>
    </div>
</div>

<style>
    .bg-passed {
        background-color: rgb(37, 143, 37);
        border-color: rgb(37, 143, 37);
    }

    .bg-running {
        background-color: rgb(221, 221, 50);
        border-color: rgb(221, 221, 50);
    }

    .bg-failed {
        background-color: rgb(185, 23, 23);
        border-color: rgb(185, 23, 23);
    }
</style>
