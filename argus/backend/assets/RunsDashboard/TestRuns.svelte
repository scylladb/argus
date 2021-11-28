<script>
    import TestRun from "./TestRun.svelte";
    import { runStore, polledRuns } from "./TestRunsSubscriber.js";
    import { StatusButtonCSSClassMap, StatusBackgroundCSSClassMap } from "./TestStatus.js";
    export let data = {};
    export let id = "";
    export let filtered = false;
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

    const titleCase = function (string) {
        return string[0].toUpperCase() + string.slice(1).toLowerCase();
    };

    polledRuns.subscribe((val) => {
        runs = val[myId] ?? runs;
    })

    const handleTestRunClick = function (e) {
        clickedTestRuns[e.target.dataset.argusTestId] = true;
    };
</script>

<div class:d-none={filtered} class="accordion-item border">
    <h4 class="accordion-header" id="heading{id}">
        <button
            class="accordion-button d-flex align-items-center"
            data-bs-toggle="collapse"
            data-bs-target="#collapse{id}"
        >
            {#if runs.length > 0}
            <span
                title={titleCase(runs[0].status)}
                class="me-2 cursor-question status-circle {StatusBackgroundCSSClassMap[runs[0].status] ?? StatusBackgroundCSSClassMap["unknown"]}"
                ></span
            >
            {/if}
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
                    <div class="container-fluid p-0 bg-light">
                        {#if clickedTestRuns[run.id]}
                            <TestRun
                                id={run.id}
                                build_number={run.build_number}
                            />
                        {/if}
                    </div>
                </div>
            {:else}
                <div class="text-muted text-center">No builds yet!</div>
            {/each}
        </div>
    </div>
</div>

<style>
    .status-circle {
        display: inline-block;
        padding: 8px;
        border-radius: 50%;
    }

    .cursor-question {
        cursor: help;
    }

</style>
