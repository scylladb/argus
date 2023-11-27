<script>
    import { createEventDispatcher, onMount, onDestroy } from "svelte";
    import queryString from "query-string";
    import { v4 as uuidv4 } from "uuid";
    import { StatusBackgroundCSSClassMap } from "../Common/TestStatus";
    import { titleCase } from "../Common/TextUtils";
    import { timestampToISODate } from "../Common/DateUtils";
    import TestRunsSelector from "./TestRunsSelector.svelte";
    import { extractBuildNumber } from "../Common/RunUtils";
    import TestRunDispatcher from "./TestRunDispatcher.svelte";
    import { isPluginSupported } from "../Common/PluginDispatch";
    import { AVAILABLE_PLUGINS } from "../Common/PluginDispatch";
    import { sendMessage } from "../Stores/AlertStore";
    import TestRunsMessage from "./TestRunsMessage.svelte";

    export let testId;
    export let listId = uuidv4();
    export let filtered = false;
    export let removableRuns = false;
    export let additionalRuns = [];
    /**
     * @type {{roles: string[]}}
     */
    let runRefreshInterval;
    let runs = [];
    let runLimit = 10;
    let testInfo;

    const states = {
        INIT: "INIT",
        INIT_RUNS: "INIT_RUNS",
        FETCH_FAILED: "FETCH_FAILED",
        FETCH_EMPTY: "FETCH_EMPTY",
        FETCH_SUCCESS: "FETCH_SUCCESS",
        FETCH_TEST_INFO_FAILED: "FETCH_TEST_INFO_FAILED",
    };
    let currentState = states.INIT;

    const stateMap = {
        [states.INIT]: {
            nextStates: [states.INIT_RUNS, states.FETCH_TEST_INFO_FAILED],
            inProgress: true,
            classes: ["text-muted"],
            message: "Loading test information...",
            onEnter: function() {
                //empty
            },
        },
        [states.INIT_RUNS]: {
            nextStates: [states.FETCH_EMPTY, states.FETCH_FAILED, states.FETCH_SUCCESS],
            inProgress: true,
            classes: ["text-muted"],
            message: "Loading...",
            onEnter: function() {
                //empty
            },
        },
        [states.FETCH_EMPTY]: {
            nextStates: [states.FETCH_FAILED, states.FETCH_SUCCESS],
            inProgress: false,
            classes: ["text-muted"],
            message: "No test runs have been submitted for this test so far!",
            onEnter: function() {
                //empty
            },
        },
        [states.FETCH_FAILED]: {
            nextStates: [states.FETCH_SUCCESS, states.FETCH_EMPTY],
            inProgress: false,
            classes: ["alert-danger"],
            message: "Failed fetching runs for this test, retrying...",
            onEnter: function() {
                //empty
            },
        },
        [states.FETCH_SUCCESS]: {
            nextStates: [],
            inProgress: false,
            classes: [],
            message: "",
            onEnter: function() {
                //empty
            },
        },
        [states.FETCH_TEST_INFO_FAILED]: {
            nextStates: [],
            inProgress: false,
            classes: ["alert-danger"],
            message: "Unable to fetch test info.",
            onEnter: function() {
                //empty
            },
        },
    };

    const setState = function(newState) {
        let curState = stateMap[currentState];
        if (!curState.nextStates.includes(newState)) return;
        currentState = newState;
        stateMap[currentState].onEnter();
    };

    const loadAdditionalRuns = function(additionalRuns) {
        return additionalRuns.reduce((acc, val) => {
            acc[val] = true;
            return acc;
        }, {});
    };

    const dispatch = createEventDispatcher();
    let selectedPlugin = "";
    let pluginFixed = false;
    let runsBody = undefined;
    let clickedTestRuns = {};
    $: clickedTestRuns = loadAdditionalRuns(additionalRuns);

    const fetchTestInfo = async function () {
        try {
            let params = queryString.stringify({
                testId: testId,
            }, { arrayFormat: "bracket" });
            let res = await fetch("/api/v1/test-info?" + params);
            if (res.status != 200) {
                throw new Error(`Network error: ${res.status}`);
            }
            let json = await res.json();
            if (json.status != "ok") {
                throw json.response;
            }

            testInfo = json.response;
            setState(states.INIT_RUNS);
        } catch (error) {
            if (error?.exception) {
                sendMessage("error", `Failed fetching test info: ${error.exception}\n${error.arguments.join(" ")}`);
            } else if (error instanceof Error) {
                sendMessage("error", error.message);
            }
            setState(states.FETCH_TEST_INFO_FAILED);
        }
    };

    const fetchTestRuns = async function () {
        try {
            let params = queryString.stringify({
                additionalRuns,
                limit: runLimit,
            }, { arrayFormat: "bracket" });
            let res = await fetch(`/api/v1/test/${testId}/runs?` + params);
            if (res.status != 200) {
                throw new Error(`Network error: ${res.status}`);
            }
            let json = await res.json();
            if (json.status != "ok") {
                throw json.response;
            }

            runs = json.response;
            if (runs.length == 0) {
                setState(states.FETCH_EMPTY);
            } else {
                setState(states.FETCH_SUCCESS);
            }
        } catch (error) {
            if (error?.exception) {
                sendMessage("error", `Failed fetching runs: ${error.exception}\n${error.arguments.join(" ")}`);
            } else if (error instanceof Error) {
                sendMessage("error", error.message);
            }
            setState(states.FETCH_FAILED);
        }
    };

    const handleIncreaseLimit = function () {
        runLimit += 10;
        fetchTestRuns();
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

    const handlePluginFixup = async function () {
        let response = await fetch(`/api/v1/test/${testId}/set_plugin`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                plugin_name: selectedPlugin
            })
        });
        if (response.status != 200) {
            sendMessage("error", "Failed adjusting plugin for this test");
        }
        let json = await response.json();
        if (json.status != "ok") {
            sendMessage("error", "Failed adjusting plugin for this test");
            console.log(json);
        }
        pluginFixed = true;
    };

    const handleIgnoreRuns = async function(e) {
        let testId = e.detail.testId;
        let reason = e.detail.reason;

        let response = await fetch("/api/v1/ignore_jobs", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                testId: testId,
                reason: reason,
            })
        });        
        
        if (response.status != 200) {
            sendMessage("error", "Failed to ignore runs for this test");
            return;
        }

        try {
            let json = await response.json();
            if (json.status != "ok") {
                sendMessage("error", "Failed to ignore runs for this test");
                console.log(json);
            }
            sendMessage("success", `Runs successfully ignored. Affected amount: ${json.response.affectedJobs}`);
            fetchTestRuns();
            dispatch("batchIgnoreDone");
        } catch(e) {
            sendMessage("error", "Error parsing response json, check console for details.");
            console.log(e);
        }
    };

    onMount(async () => {
        await fetchTestInfo();
        if (testInfo) {
            fetchTestRuns();
            runRefreshInterval = setInterval(async () => {
                fetchTestRuns();
            }, 120 * 1000);
        }
    });

    onDestroy(() => {
        if (runRefreshInterval) {
            clearInterval(runRefreshInterval);
        }
    });
</script>

<div class:d-none={filtered} class="accordion-item border-none  bg-main mb-1">
{#if testInfo}
    <h4
        class="accordion-header border-none"
        id="heading{listId}"
    >
        <button
            class="accordion-button rounded d-flex align-items-center { removableRuns ? "shadow" : "p-2"}"
            data-bs-toggle="{ removableRuns ? "collapse" : ""}"
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
        {#if !isPluginSupported(testInfo.test.plugin_name)}
            <div class="rounded shadow-sm bg-white p-2 text-center">
                <span class="fw-bold">Unsupported plugin</span> <span class="d-inline-block text-danger bg-light-one rounded p-1">{testInfo.test.plugin_name ? testInfo.test.plugin_name : "#empty-test-name"}</span>
            </div>
                <div>
                    {#if !pluginFixed}
                        <div class="p-2 alert alert-warning my-2">This looks like a newly added test and it will need to have its plugin name specified. If you know which plugin this test should use, select it from the list below and click save.</div>
                        <div class="form-group mb-2">
                            <label for="" class="form-label">Plugin</label>
                            <select id="" class="form-select" bind:value={selectedPlugin}>
                                {#each Object.keys(AVAILABLE_PLUGINS) as plugin}
                                    <option value={plugin}
                                        >{plugin}</option
                                    >
                                {/each}
                            </select>
                        </div>
                        <div>
                            <button class="btn btn-success w-100" on:click={handlePluginFixup}>Save</button>
                        </div>
                    {:else}
                        <div>
                            Refresh the page to see updated changes.
                        </div>
                    {/if}
                </div>
        {/if}
        {#if runs.length > 0}
            <div class="p-2" bind:this={runsBody}>
                <TestRunsSelector
                    {runs}
                    {testInfo}
                    bind:clickedTestRuns={clickedTestRuns}
                    on:runClick={handleTestRunClick}
                    on:closeRun={handleTestRunClose}
                    on:increaseLimit={handleIncreaseLimit}
                    on:ignoreRuns={handleIgnoreRuns}
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
                                    on:investigationStatusChange
                                />
                            {/if}
                        </div>
                    </div>
                {/each}
            </div>
        {:else}
            <TestRunsMessage state={stateMap[currentState]}>
                <div>
                    <a class="link link-primary" href="{testInfo.test.build_system_url}">Jenkins</a>
                </div>
            </TestRunsMessage>
        {/if}
    </div>
{:else}
    <div class="d-flex">
        <div class="flex-fill">
            <TestRunsMessage state={stateMap[currentState]}>
                <div>
                    Test ID: {testId}
                </div>
                {#if removableRuns}
                <div class="mx-2 p-2">
                    <button
                        class="d-inline-block btn btn-secondary"
                        on:click={() => { dispatch("testRunRemove", { testId: testId }); }}
                    >
                        Close
                    </button>
                </div>
                {/if}
            </TestRunsMessage>
        </div>
    </div>
{/if}
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
