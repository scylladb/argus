<script>
    import { v4 as uuidv4 } from "uuid";
    import { runStore, polledRuns, TestRunsEventListener } from "../Stores/TestRunsSubscriber";
    import { StatusButtonCSSClassMap, StatusBackgroundCSSClassMap } from "../Common/TestStatus";
    import TestRun from "../TestRun/TestRun.svelte";
    export let data = {};
    export let listId = uuidv4();
    export let filtered = false;
    console.log(data);
    let clickedTestRuns = {};
    let testInfo = data.test;
    let runs = data.runs;
    let releaseName = data.release
    let myId = `${releaseName}/${testInfo}`;

    runStore.update((val) => {
        val[myId] = [releaseName, testInfo]
        return val;
    });

    const titleCase = function (string) {
        return string[0].toUpperCase() + string.slice(1).toLowerCase();
    };

    polledRuns.subscribe((val) => {
        runs = val[myId] ?? runs;
    })

    TestRunsEventListener.update(val => {
        return {
            type: "fetch",
            args: []
        };
    });

    const handleTestRunClick = function (e) {
        clickedTestRuns[e.target.dataset.argusTestId] = true;
    };
</script>

<div class:d-none={filtered} class="accordion-item border">
    <h4 class="accordion-header" id="heading{listId}">
        <button
            class="accordion-button d-flex align-items-center"
            data-bs-toggle="collapse"
            data-bs-target="#collapse{listId}"
        >
            {#if runs.length > 0}
            <span
                title={titleCase(runs[0].status)}
                class="me-2 cursor-question status-circle {StatusBackgroundCSSClassMap[runs[0].status] ?? StatusBackgroundCSSClassMap["unknown"]}"
                ></span
            >
            {/if}
            <div>{testInfo} ({releaseName})</div>
            {#if runs.length > 0}
            <div class="ms-auto flex-fill text-end">Last run: #{runs[0].build_number}</div>
            <div class="mx-2">Date: {new Date(runs[0].start_time * 1000).toISOString()}</div>
            {/if}

        </button>
    </h4>
    <div class="accordion-collapse collapse show" id="collapse{listId}">
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
                <div class="text-muted text-center">Loading...</div>
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
