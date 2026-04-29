    <script lang="ts">
    import { onMount, onDestroy, createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import {
        faBoxes,
        faCodeBranch,
        faComments,
        faExclamationTriangle,
        faInfoCircle,
        faRefresh,
        faTimes,
    } from "@fortawesome/free-solid-svg-icons";
    import ActivityTab from "./ActivityTab.svelte";
    import TestRunComments from "./TestRunComments.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { fetchRun } from "../Common/RunUtils";
    import RunStatusButton from "./RunStatusButton.svelte";
    import RunInvestigationStatusButton from "./RunInvestigationStatusButton.svelte";
    import RunAssigneeSelector from "./RunAssigneeSelector.svelte";
    import DriverMatrixRunInfo from "./DriverMatrixRunInfo.svelte";
    import DriverMatrixTestCollection from "./DriverMatrixTestCollection.svelte";
    import IssueTab from "./IssueTab.svelte";

    interface Props {
        runId?: string;
        buildNumber?: any;
        testInfo?: any;
        tab?: string;
    }

    let {
        runId = "",
        buildNumber = $bindable(-1),
        testInfo = {},
        tab = ""
    }: Props = $props();
    const dispatch = createEventDispatcher();
    let testRun = $state(undefined);
    let runRefreshInterval;
    let activeTab = $state(tab.toLowerCase() || "details");
    let failedToLoad = $state(false);

    // Track which tabs have been visited
    let visitedTabs = $state({});
    visitedTabs[tab.toLowerCase() || "details"] = true;

    const setActiveTab = (tabName) => {
        tabName = tabName.toLowerCase();
        if (tabName !== activeTab) {
            activeTab = tabName;
            visitedTabs[tabName] = true;
            if (!window.location.pathname.startsWith("/workspace")) {
                const newUrl = `/tests/${testInfo.test.plugin_name}/${runId}/${tabName}`;
                history.replaceState({}, "", newUrl);
            }
        }
    };

    const fetchTestRunData = async function () {
        try {
            let run = await fetchRun(testInfo.test.plugin_name, runId);
            testRun = run;
            if (!testRun) {
                failedToLoad = true;
                return;
            }
            if (buildNumber == -1) {
                buildNumber = parseInt(
                    testRun.build_job_url.split("/").reverse()[1]
                );
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching test run data.\nMessage: ${error.response.arguments[0]}`,
                    "DriverMatrixTestRun::fetchTestRunData"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test run data fetch",
                    "DriverMatrixTestRun::fetchTestRunData"
                );
            }
        }
    };

    onMount(() => {
        fetchTestRunData();

        runRefreshInterval = setInterval(() => {
            fetchTestRunData();
        }, 1000 * 300);
    });

    onDestroy(() => {
        if (runRefreshInterval) clearInterval(runRefreshInterval);
    });
</script>

<div class="border rounded shadow-sm testrun-card mb-4 top-bar">
    <div class="d-flex px-2 py-2 mb-1 border-bottom bg-white ">
        <div class="p-1 min-width-0 text-truncate">
            {#if testRun}
                <a class="link-dark" href="/tests/{testInfo.test.plugin_name}/{testRun.id}">
                    {testRun.build_id}#{buildNumber}
                </a>
            {/if}
        </div>
        <div class="ms-auto text-end flex-shrink-0">
            <button class="btn btn-sm btn-outline-dark" title="Refresh" onclick={() => {
                fetchTestRunData();
            }}
                ><Fa icon={faRefresh} /></button
            >
        </div>
        <div class="ms-2 text-end flex-shrink-0">
            <button class="btn btn-sm btn-outline-dark" title="Close" onclick={() => {
                dispatch("closeRun", { id: runId });
            }}
                ><Fa icon={faTimes} /></button
            >
        </div>
    </div>
    {#if testRun}
        <div class="p-2">
            <div class="row p-2">
                <div class="col-12 col-md-6">
                    <div class="d-flex align-items-center">
                        <RunStatusButton {testRun} on:statusUpdate={(e) => {
                            testRun.status = e.detail.status;
                            dispatch("runStatusChange");
                        }} />
                        <RunInvestigationStatusButton {testRun} on:investigationStatusChange={(e) => {
                            testRun.investigation_status = e.detail.status;
                            dispatch("investigationStatusChange", e.detail);
                        }} />
                    </div>
                </div>
                <div class="col-12 col-md-6">
                    <RunAssigneeSelector {testRun} on:assigneeUpdate={(e) => {
                        testRun.assignee = e.detail.assignee;
                    }} />
                </div>
            </div>
            <div class="argus-tab-bar" role="tablist">
                    <button class="argus-tab" class:active={activeTab === 'details'} type="button" role="tab" onclick={() => setActiveTab("details")}>
                        <Fa icon={faInfoCircle}/> Details
                    </button>
                    <button class="argus-tab" class:active={activeTab === 'tests'} type="button" role="tab" onclick={() => setActiveTab("tests")}>
                        <Fa icon={faBoxes}/> Tests
                    </button>
                    <button class="argus-tab" class:active={activeTab === 'discuss'} type="button" role="tab" onclick={() => setActiveTab("discuss")}>
                        <Fa icon={faComments}/> Discussion
                    </button>
                    <button class="argus-tab" class:active={activeTab === 'issues'} type="button" role="tab" onclick={() => setActiveTab("issues")}>
                        <Fa icon={faCodeBranch}/> Issues
                    </button>
                    <button class="argus-tab" class:active={activeTab === 'activity'} type="button" role="tab" onclick={() => setActiveTab("activity")}>
                        <Fa icon={faExclamationTriangle}/> Activity
                    </button>
                </div>
                <div class="argus-tab-select">
                    <select onchange={(e) => setActiveTab(e.currentTarget.value)} value={activeTab}>
                        <option value="details">Details</option>
                        <option value="tests">Tests</option>
                        <option value="discuss">Discussion</option>
                        <option value="issues">Issues</option>
                        <option value="activity">Activity</option>
                    </select>
                </div>
            <div
                class="argus-tab-content"
                id="nav-tabContent-{runId}"
            >
                <div role="tabpanel" style:display={activeTab === 'details' ? "block" : "none"}>
                    <DriverMatrixRunInfo testRun={testRun} {testInfo}/>
                </div>
                <div role="tabpanel" style:display={activeTab === 'tests' ? "block" : "none"}>
                    <DriverMatrixTestCollection collections={testRun.test_collection} testId={testRun.id}/>
                </div>
                <div role="tabpanel" style:display={activeTab === 'discuss' ? "block" : "none"}>
                    {#if visitedTabs['discuss']}
                        <TestRunComments {testRun} {testInfo}/>
                    {/if}
                </div>
                <div role="tabpanel" style:display={activeTab === 'issues' ? "block" : "none"}>
                    <div class="py-2 bg-white">
                        {#if visitedTabs['issues']}
                            <IssueTab {testInfo} {runId} />
                        {/if}
                    </div>
                </div>
                <div role="tabpanel" style:display={activeTab === 'activity' ? "block" : "none"}>
                    {#if visitedTabs['activity']}
                        <ActivityTab id={runId} />
                    {/if}
                </div>
            </div>
        </div>
    {:else if failedToLoad}
        <div
            class="text-center p-2 m-1 d-flex align-items-center justify-content-center"
        >
            <span class="fs-4"
                >Run not found.</span
            >
        </div>
    {:else}
        <div
            class="text-center p-2 m-1 d-flex align-items-center justify-content-center"
        >
            <span class="spinner-border me-4"></span><span class="fs-4"
                >Loading...</span
            >
        </div>
    {/if}
</div>

<style>
    .testrun-card {
        background-color: #ededed;
    }

    .top-bar {
        overflow: hidden;
    }

    :global([data-bs-theme="dark"]) .testrun-card {
        background-color: #2b3035;
    }
</style>
