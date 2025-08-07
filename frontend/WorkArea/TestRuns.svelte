<script>
    import { run as run_1 } from 'svelte/legacy';

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
    import { faGear, faPlay, faTimes } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import { Collapse } from "bootstrap";
    import JobConfigureModal from "./JobConfigureModal.svelte";
    import { applicationCurrentUser } from "../argus";
    import ResultsGraphs from "../TestRun/ResultsGraphs.svelte";
    import { faCopy } from "@fortawesome/free-regular-svg-icons";
    import JenkinsCloneModal from "../TestRun/Jenkins/JenkinsCloneModal.svelte";
    import JenkinsBuildModal from "../TestRun/Jenkins/JenkinsBuildModal.svelte";

    /**
     * @typedef {Object} Props
     * @property {any} testId
     * @property {any} tab
     * @property {any} [listId]
     * @property {boolean} [filtered]
     * @property {boolean} [removableRuns]
     * @property {any} [additionalRuns]
     */

    /** @type {Props} */
    let {
        testId,
        tab,
        listId = uuidv4(),
        filtered = false,
        removableRuns = false,
        additionalRuns = []
    } = $props();
    /**
     * @type {{roles: string[]}}
     */
    let runRefreshInterval;
    let runs = $state([]);
    let runLimit = 10;
    let testInfo = $state();

    const states = {
        INIT: "INIT",
        INIT_RUNS: "INIT_RUNS",
        FETCH_FAILED: "FETCH_FAILED",
        FETCH_EMPTY: "FETCH_EMPTY",
        FETCH_SUCCESS: "FETCH_SUCCESS",
        FETCH_TEST_INFO_FAILED: "FETCH_TEST_INFO_FAILED",
    };
    let currentState = $state(states.INIT);

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
    let selectedPlugin = $state("");
    let configureRequested = $state(false);
    let cloneRequested = $state(false);
    let execRequested = $state(false);
    let open = $state(true);
    let pluginFixed = $state(false);
    let runsBody = $state(undefined);
    let clickedTestRuns = $state({});
    let clickedGraph = $state(false);
    run_1(() => {
        clickedTestRuns = loadAdditionalRuns(additionalRuns);
    });

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
                sendMessage("error", `Failed fetching test info: ${error.exception}\n${error.arguments.join(" ")}`, "TestRuns::fetchTestInfo");
            } else if (error instanceof Error) {
                sendMessage("error", error.message, "TestRuns::fetchTestInfo");
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
                sendMessage("error", `Failed fetching runs: ${error.exception}\n${error.arguments.join(" ")}`, "TestRuns::fetchTestRuns");
            } else if (error instanceof Error) {
                sendMessage("error", error.message, "TestRuns::fetchTestRuns");
            }
            setState(states.FETCH_FAILED);
        }
    };

    const handleIncreaseLimit = function () {
        runLimit += 10;
        fetchTestRuns();
    };

    const handleTestRunClick = async function (e) {
        let runId = e.detail.runId;
        let collapse = runsBody.querySelector(`#collapse${runId}`);
        if (!collapse) {
            additionalRuns.push(runId);
            await fetchTestRuns();
            loadAdditionalRuns(additionalRuns);
            collapse = runsBody.querySelector(`#collapse${runId}`);
        }

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

    const handleShowGraph = function (e) {
        clickedGraph = !clickedGraph;
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
            sendMessage("error", "Failed adjusting plugin for this test", "TestRuns::handlePluginFixup");
        }
        let json = await response.json();
        if (json.status != "ok") {
            sendMessage("error", "Failed adjusting plugin for this test", "TestRuns::handlePluginFixup");
            console.log(json);
        }
        pluginFixed = true;
        main();
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
            sendMessage("error", "Failed to ignore runs for this test", "TestRuns::handleIgnoreRuns");
            return;
        }

        try {
            let json = await response.json();
            if (json.status != "ok") {
                sendMessage("error", "Failed to ignore runs for this test");
                console.log(json);
            }
            sendMessage("success", `Runs successfully ignored. Affected amount: ${json.response.affectedJobs}`, "TestRuns::handleIgnoreRuns");
            fetchTestRuns();
            dispatch("batchIgnoreDone");
        } catch(e) {
            sendMessage("error", "Error parsing response json, check console for details.", "TestRuns::handleIgnoreRuns");
            console.log(e);
        }
    };

    const main = async () => {
        await fetchTestInfo();
        if (testInfo) {
            fetchTestRuns();
            runRefreshInterval = setInterval(async () => {
                fetchTestRuns();
            }, 120 * 1000);
        }
    };

    onMount(main);

    onDestroy(() => {
        if (runRefreshInterval) {
            clearInterval(runRefreshInterval);
        }
    });
</script>

<div class:d-none={filtered} class="accordion-item border-none  bg-main mb-1">
{#if testInfo}
    <div
        class="border-none mb-2"
    >
        <div
            class="btn w-100 rounded d-flex align-items-center { removableRuns ? "shadow-sm" : "p-2"}"
            class:btn-light={!open}
            class:btn-testruns-open={open}
            role="button"
            tabindex="0"
            onkeydown={() => {}}
            onclick={() => {
                open = !open;
                new Collapse(`#collapse-${listId}`).toggle();
            }}
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
                <div class="btn-group">
                    {#if applicationCurrentUser.roles.some(v => ["ROLE_ADMIN", "ROLE_MANAGER"].includes(v)) || testInfo.release.name.includes("staging")}
                        <button class="btn" onclick={(e) => {configureRequested = true; e.stopPropagation();}}><Fa icon={faGear}/></button>
                    {/if}
                    <button class="btn" onclick={(e) => {execRequested = true; e.stopPropagation();}}><Fa icon={faPlay} /></button>
                    <button class="btn" onclick={(e) => {cloneRequested = true; e.stopPropagation();}}><Fa icon={faCopy} /></button>
                </div>
            {#if removableRuns}
                <div class="me-2" class:ms-1={runs.length > 0} class:ms-auto={runs.length == 0} >
                    <button
                        class="btn"
                        onclick={(e) => { dispatch("testRunRemove", { testId: testId }); e.stopPropagation(); }}
                    >
                        <Fa icon={faTimes}/>
                    </button>
                </div>
            {/if}
        </div>
    </div>
    {#if configureRequested}
        <JobConfigureModal
            testName={testInfo.test.pretty_name || testInfo.test.name}
            buildId={testInfo.test.build_system_id}
            on:configureCancel={() => (configureRequested = false)}
            on:settingsFinished={() => (configureRequested = false)}
        />
    {/if}
    {#if cloneRequested}
        <JenkinsCloneModal
            buildId={testInfo.test.build_system_id}
            buildNumber={runs.length > 0 ? extractBuildNumber(runs[0]) : -1}
            pluginName={testInfo.test.plugin_name}
            testId={testInfo.test.id}
            releaseId={testInfo.release.id}
            groupId={testInfo.group.id}
            oldTestName={testInfo.test.name}
            on:cloneCancel={() => (cloneRequested = false)}
            on:cloneComplete={(e) => { cloneRequested = false; dispatch("cloneSelect", { testId: e.detail.testId }); }}
        />
    {/if}
    {#if execRequested}
        <JenkinsBuildModal
            buildId={testInfo.test.build_system_id}
            buildNumber={runs.length > 0 ? extractBuildNumber(runs[0]) : undefined}
            pluginName={testInfo.test.plugin_name}
            on:rebuildCancel={() => (execRequested = false)}
            on:rebuildComplete={() => (execRequested = false)}
        />
    {/if}
    <div class="collapse show bg-main shadow-sm rounded" id="collapse-{listId}">
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
                            <button class="btn btn-success w-100" onclick={handlePluginFixup}>Save</button>
                        </div>
                    {:else}
                        <div>
                            Refresh the page to see updated changes.
                        </div>
                    {/if}
                </div>
        {/if}
        {#if runs.length > 0}
            <div class="" bind:this={runsBody}>
                <TestRunsSelector
                    {runs}
                    {testInfo}
                    {testId}
                    bind:clickedTestRuns={clickedTestRuns}
                    on:runClick={handleTestRunClick}
                    on:closeRun={handleTestRunClose}
                    on:increaseLimit={handleIncreaseLimit}
                    on:ignoreRuns={handleIgnoreRuns}
                    on:fetchNewRuns={fetchTestRuns}
                    on:showGraph={handleShowGraph}
                />
                {#if clickedGraph}
                <div class="collapse mb-2 show" id="collapse-graphs" >
                        <div class="container-fluid p-1 bg-light" >
                            <ResultsGraphs test_id={testInfo.test.id}
                                           bind:clickedTestRuns={clickedTestRuns}
                                           on:runClick={handleTestRunClick}/>
                        </div>
                    </div>
                    {/if}
                {#each runs as run (run.id)}
                    <div class:show={clickedTestRuns[run.id]} class="collapse mb-2" id="collapse{run.id}">
                        <div class="container-fluid p-1 bg-light">
                            {#if clickedTestRuns[run.id]}
                                <TestRunDispatcher
                                    runId={run.id}
                                    {testInfo}
                                    tab={tab}
                                    buildNumber={extractBuildNumber(run)}
                                    on:closeRun={handleTestRunClose}
                                    on:investigationStatusChange
                                    on:runStatusChange={fetchTestRuns}
                                    on:cloneComplete={(e) => dispatch("cloneSelect", { testId: e.detail.testId })}
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
                        onclick={() => { dispatch("testRunRemove", { testId: testId }); }}
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
