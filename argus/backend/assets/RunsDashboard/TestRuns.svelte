<script>
    import TestRun from "./TestRun.svelte";
    import { runStore, polledRuns } from "./TestRunsSubscriber.js";
    import { StatusButtonCSSClassMap } from "./TestStatus.js";
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
                            class="btn {StatusButtonCSSClassMap[run.status]}"
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
                    <div class="card card-body shadow-sm">
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

</style>
