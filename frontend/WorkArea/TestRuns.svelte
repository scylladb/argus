<script>
    import { createEventDispatcher } from "svelte";
    import { v4 as uuidv4 } from "uuid";
    import { StatusBackgroundCSSClassMap } from "../Common/TestStatus";
    import { titleCase } from "../Common/TextUtils";
    import { timestampToISODate } from "../Common/DateUtils";
    import TestRunsSelector from "./TestRunsSelector.svelte";
    import { extractBuildNumber } from "../Common/RunUtils";
    import TestRunDispatcher from "./TestRunDispatcher.svelte";
import { isPluginSupported } from "../Common/PluginDispatch";

    export let testId;
    export let listId = uuidv4();
    export let filtered = false;
    export let removableRuns = false;
    export let additionalRuns = [];

    const dispatch = createEventDispatcher();
    let runsBody = undefined;
    let clickedTestRuns = additionalRuns.reduce((acc, val) => {
        acc[val] = true;
        return acc;
    }, {});

    const fetchTestInfo = async function () {
        let params = new URLSearchParams({
            testId: testId,
        });
        let res = await fetch("/api/v1/test-info?" + params);
        if (res.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await res.json();
        if (json.status != "ok") {
            return Promise.reject(json.exception);
        }
        return json.response;
    };

    const fetchTestRuns = async function () {
        let additionals = additionalRuns.map(v => `additionalRuns[]=${v}`).join("&");
        let res = await fetch(`/api/v1/test/${testId}/runs?` + additionals);
        if (res.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await res.json();
        if (json.status != "ok") {
            return Promise.reject(json.exception);
        }

        return json.response;
    };

    const handleTestRunClick = function (e) {
        let runId = e.detail.runId;
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
</script>

<div class:d-none={filtered} class="accordion-item border-none  bg-main mb-1">
{#await Promise.all([fetchTestInfo(), fetchTestRuns()])}
    <div class="d-flex rounded shadow justify-content-center align-items-center bg-light-two p-4">
        <div class="spinner-border"></div>
        <div class="ms-2">Loading test information...</div>
    </div>
{:then [testInfo, runs]}
    <h4
        class="accordion-header border-none"
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
                <div>{testInfo.test.name} ({testInfo.release.name}/{testInfo.group.name})</div>
            {#if runs.length > 0}
                <div class="ms-auto flex-fill text-end">{timestampToISODate(runs[0].start_time)}</div>
                <div class="mx-2">#{extractBuildNumber(runs[0])}</div>
            {/if}
            {#if removableRuns}
                <div class="mx-2 text-end" class:flex-fill={runs.length == 0}>
                    <div
                        class="d-inline-block btn btn-close"
                        role="button"
                        on:click={() => { dispatch("testRunRemove", { testId: testId }); }}
                    >
                    </div>
                </div>
            {/if}
        </button>
    </h4>
    <div class="accordion-collapse collapse show" id="collapse{listId}">
        {#await fetchTestRuns()}
            <div class="text-muted text-center m-3"><span class="spinner-border spinner-border-sm"></span> Loading...</div>
        {:then runs}
            <div class="p-2" bind:this={runsBody}>
                {#if isPluginSupported(testInfo.test.plugin_name)}
                    <div class="rounded shadow-sm bg-white p-2 text-center">
                        <span class="fw-bold">Unsupported plugin</span> <span class="d-inline-block text-danger bg-light-one rounded p-1">{testInfo.test.plugin_name}</span>
                    </div>
                {/if}
                <TestRunsSelector
                    {runs}
                    {testInfo}
                    bind:clickedTestRuns={clickedTestRuns}
                    on:runClick={handleTestRunClick}
                    on:closeRun={handleTestRunClose}
                />
                {#each runs as run (run.id)}
                    <div class:show={clickedTestRuns[run.id]} class="collapse mb-2" id="collapse{run.id}">
                        <div class="container-fluid p-0 bg-light">
                            {#if clickedTestRuns[run.id]}
                                <TestRunDispatcher
                                    runId={run.id}
                                    {testInfo}
                                    buildNumber={extractBuildNumber(run)}
                                    on:closeRun={handleTestRunClose}
                                />
                            {/if}
                        </div>
                    </div>
                {/each}
            </div>
        {/await}
    </div>
{/await}
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


    .border-none {
        border-style: none;
    }

</style>
