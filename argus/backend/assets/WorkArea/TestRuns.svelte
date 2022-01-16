<script>
    import { createEventDispatcher, onDestroy } from "svelte";
    import { v4 as uuidv4 } from "uuid";
    import { runStore, polledRuns, TestRunsEventListener } from "../Stores/TestRunsSubscriber";
    import { StatusButtonCSSClassMap, StatusBackgroundCSSClassMap } from "../Common/TestStatus";
    import Fa from "svelte-fa";
    import { faTrash } from "@fortawesome/free-solid-svg-icons"
    import { timestampToISODate } from "../Common/DateUtils";
    import TestRun from "../TestRun/TestRun.svelte";
    export let data = {};
    export let listId = uuidv4();
    export let filtered = false;
    export let removableRuns = false;
    const dispatch = createEventDispatcher();
    let clickedTestRuns = {};
    let testInfo = data.test;
    let runs = data.runs;
    let noRuns = false;
    let updateCounter = 0;
    let releaseName = data.release;
    let myId = `${releaseName}/${testInfo}`;

    runStore.update((val) => {
        val[myId] = [releaseName, testInfo]
        return val;
    });

    const titleCase = function (string) {
        return string[0].toUpperCase() + string.slice(1).toLowerCase();
    };

    const polledRunsUnsub = polledRuns.subscribe((val) => {
        runs = val[myId] ?? runs;
        updateCounter++;
        if (runs.length == 0 && updateCounter > 1) {
            noRuns = true;
        } else {
            noRuns = false;
        }
    })

    TestRunsEventListener.update(val => {
        return {
            type: "fetch",
            args: []
        };
    });

    const handleTestRunClick = function (e) {
        if (clickedTestRuns[e.target.dataset.argusTestId]) {
            clickedTestRuns[e.target.dataset.argusTestId] = false;
            return;
        }
        clickedTestRuns[e.target.dataset.argusTestId] = true;
    };

    onDestroy(() => {
        TestRunsEventListener.update(() => {
            return {
                type: "unsubscribe",
                id: myId
            };
        });
        polledRunsUnsub();
    });
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
            <div class="ms-auto flex-fill text-end">{timestampToISODate(runs[0].start_time * 1000)}</div>
            <div class="mx-2">#{runs[0].build_number}</div>
            {/if}
            {#if removableRuns}
            <div class="mx-2 text-end" class:flex-fill={runs.length == 0}>
                <div
                    class="d-inline-block btn btn-danger"
                    on:click={() => { dispatch("testRunRemove", { runId: myId })}}
                >
                    <Fa icon={faTrash}/>
                </div>
            </div>
            {/if}

        </button>
    </h4>
    <div class="accordion-collapse collapse show" id="collapse{listId}">
        {#if noRuns}
        <div class="text-muted text-center m-3">No runs for this test!</div>
        {:else if !noRuns && runs.length == 0}
        <div class="text-muted text-center m-3"><span class="spinner-border spinner-border-sm"></span> Loading...</div>
        {:else}
        <div class="p-2">
            <p class="p-2">
                {#each runs as run}
                    <div class="me-2 d-inline-block">
                        <button
                            class:border-active={clickedTestRuns[run.id]}
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
            {/each}
        </div>
        {/if}
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

    .border-active {
        border: 3px solid rgb(84, 192, 255);
    }

</style>
