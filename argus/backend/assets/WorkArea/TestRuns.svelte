<script>
    import { createEventDispatcher, onDestroy, onMount } from "svelte";
    import { v4 as uuidv4 } from "uuid";
    import { runStore, polledRuns, TestRunsEventListener } from "../Stores/TestRunsSubscriber";
    import { StatusButtonCSSClassMap, StatusBackgroundCSSClassMap } from "../Common/TestStatus";
    import { timestampToISODate } from "../Common/DateUtils";
    import TestRun from "../TestRun/TestRun.svelte";
    export let data = {};
    export let listId = uuidv4();
    export let filtered = false;
    export let removableRuns = false;
    const dispatch = createEventDispatcher();
    let clickedTestRuns = {};
    let testName = data.test;
    let groupName = data.group
    let runs = [];
    let noRuns = false;
    let updateCounter = 0;
    let releaseName = data.release;
    let myId = `${releaseName}/${groupName}/${testName}`;
    let sticky = false;
    let header = undefined;
    let runsBody = undefined;

    runStore.update((val) => {
        val[myId] = data.build_system_id;
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

    const handleTestRunClick = function (runId, event) {
        let collapse = runsBody.querySelector(`#collapse${runId}`);
        if (clickedTestRuns[runId]) {
            collapse.scrollIntoView({ behaviour: "smooth" });
            return;
        }
        clickedTestRuns[runId] = true;
        collapse.classList.add("show");
    };

    const handleTestRunClose = function (e) {
        let id = e.detail.id;
        if (!id) return;
        let collapse = runsBody.querySelector(`#collapse${id}`);
        collapse.classList.remove("show");
        clickedTestRuns[id] = false;
    };

    onMount(() => {
        let observer = new IntersectionObserver((entries, observer) => {
            let entry = entries[0];
            if (!entry) return;
            if (entry.intersectionRatio == 0) {
                sticky = true;
            } else {
                sticky = false;
            }
        }, {
            threshold: [0, 0.25, 0.5, 0.75, 1]
        })
        observer.observe(header);
    })

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

<div class:d-none={filtered} class="accordion-item border-none  bg-main mb-1">
    <h4
        class="accordion-header border-none"
        bind:this={header}
        id="heading{listId}"
    >
        <button
            class="accordion-button rounded shadow d-flex align-items-center"
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
            <div>{testName} ({releaseName}/{groupName})</div>
            {#if runs.length > 0}
            <div class="ms-auto flex-fill text-end">{timestampToISODate(runs[0].start_time * 1000)}</div>
            <div class="mx-2">#{runs[0].build_number}</div>
            {/if}
            {#if removableRuns}
            <div class="mx-2 text-end" class:flex-fill={runs.length == 0}>
                <div
                    class="d-inline-block btn btn-close"
                    role="button"
                    on:click={() => { dispatch("testRunRemove", { runId: myId })}}
                >
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
        <div class="p-2" bind:this={runsBody}>
            <p class="p-2 bg-main" class:sticky={sticky} class:border={sticky} class:shadow={sticky}>
                {#if sticky}
                <div class="mb-1 p-1">
                    {testName} ({releaseName}/{groupName})
                </div>
                {/if}
                {#each runs as run}
                    <div class="me-2 d-inline-block">
                        <button
                            class:active={clickedTestRuns[run.id]}
                            class="btn {StatusButtonCSSClassMap[run.status]}"
                            type="button"
                            on:click={(event) => handleTestRunClick(run.id, event)}
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
                                on:closeRun={handleTestRunClose}
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

    .active::before {
        font-family: "Noto Sans Packaged", "Noto Sans", sans-serif;
        content: "● ";
    }

    .sticky {
        position: sticky;
        top: 12px;
        z-index: 999;
        margin: 1em;
        border-radius: 4px;
    }

    .border-none {
        border-style: none;
    }

</style>
