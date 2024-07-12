    <script>
    import { onMount, onDestroy, createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import {
        faBox,
        faClipboard,
        faCloud,
        faCodeBranch,
        faComments,
        faExclamationTriangle,
        faImages,
        faInfoCircle,
        faRefresh,
        faRssSquare,
        faSpider,
        faTable,
        faTimes,
    } from "@fortawesome/free-solid-svg-icons";
    import ResourcesInfo from "./ResourcesInfo.svelte";
    import NemesisTable from "./NemesisTable.svelte";
    import ActivityTab from "./ActivityTab.svelte";
    import TestRunInfo from "./TestRunInfo.svelte";
    import Screenshots from "./Screenshots.svelte";
    import TestRunComments from "./TestRunComments.svelte";
    import IssueTemplate from "./IssueTemplate.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { fetchRun } from "../Common/RunUtils";
    import RunStatusButton from "./RunStatusButton.svelte";
    import RunInvestigationStatusButton from "./RunInvestigationStatusButton.svelte";
    import RunAssigneeSelector from "./RunAssigneeSelector.svelte";
    import HeartbeatIndicator from "./HeartbeatIndicator.svelte";
    import EventsTab from "./EventsTab.svelte";
    import ArtifactTab from "./ArtifactTab.svelte";
    import IssueTab from "./IssueTab.svelte";
    import { SubtestTabBodyComponents, SubtestTabComponents, Subtests } from "./SCTSubTests/Subtest";
    import PackagesInfo from "./PackagesInfo.svelte";
    import queryString from "query-string";
    import JUnitResults from "./jUnitResults.svelte";
    import ResultsTab from "./ResultsTab.svelte";
    export let runId = "";
    export let buildNumber = -1;
    export let testInfo = {};
    const dispatch = createEventDispatcher();
    let testRun = undefined;
    let runRefreshInterval;
    let activityOpen = false;
    let resultsOpen = false;
    let eventsOpen = false;
    let commentsOpen = false;
    let issuesOpen = false;
    let artifactTabOpened = false;
    let failedToLoad = false;
    let jUnitFetched = false;
    let jUnitResults = [];

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
            fetchJunitReports();
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching test run data.\nMessage: ${error.response.arguments[0]}`,
                    "SCTTestRun::fetchTestRunData"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test run data fetch",
                    "SCTTestRun::fetchTestRunData"
                );
                console.log(error);
            }
        }
    };

    const fetchJunitReports = async function () {
        try {
            let res = await fetch(`/api/v1/client/sct/${testRun.id}/junit/get_all`);
            if (res.status != 200) {
                throw new Error(`Network error: ${res.status}`);
            }
            let json = await res.json();
            if (json.status != "ok") {
                throw json.response;
            }
            jUnitFetched = true;
            jUnitResults = json.response;
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching test run junit results data.\nMessage: ${error.response.arguments[0]}`,
                    "SCTTestRun::fetchJunitReports"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test run junit results data fetch",
                    "SCTTestRun::fetchJunitReports"
                );
                console.log(error);
            }
        }
    };

    onMount(() => {
        fetchTestRunData();

        runRefreshInterval = setInterval(() => {
            fetchTestRunData();
        }, 1000 * 30);
    });

    onDestroy(() => {
        if (runRefreshInterval) clearInterval(runRefreshInterval);
    });
</script>

<div class="border rounded shadow-sm testrun-card mb-4 top-bar">
    <div class="d-flex px-2 py-2 mb-1 border-bottom bg-white ">
        <div class="p-1">
            {#if testRun}
                <a class="link-dark" href="/test/{testRun.test_id}/runs?additionalRuns[]={testRun.id}">
                    {testRun.build_id}#{buildNumber}
                </a>
            {/if}
        </div>
        <div class="ms-auto text-end">
            <button class="btn btn-sm btn-outline-dark" title="Refresh" on:click={() => {
                fetchTestRunData();
            }}
                ><Fa icon={faRefresh} /></button
            >
        </div>
        <div class="ms-2 text-end">
            <button class="btn btn-sm btn-outline-dark" title="Close" on:click={() => {
                dispatch("closeRun", { id: runId });
            }}
                ><Fa icon={faTimes} /></button
            >
        </div>
    </div>
    {#if testRun}
        <div class="p-2">
            <div class="row p-2">
                <div class="col-6">
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
                <div class="col-6">
                    <RunAssigneeSelector {testRun} on:assigneeUpdate={(e) => {
                        testRun.assignee = e.detail.assignee;
                    }} />
                    <HeartbeatIndicator {testRun} />
                </div>
            </div>
            <nav>
                <div class="nav nav-tabs" id="nav-tab-{runId}" role="tablist">
                    <button
                        class="nav-link active"
                        id="nav-details-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-details-{runId}"
                        type="button"
                        role="tab"
                        ><Fa icon={faInfoCircle}/> Details</button
                    >
                    {#if testRun.subtest_name && Object.values(Subtests).includes(testRun.subtest_name)}
                        <svelte:component this={SubtestTabComponents[testRun.subtest_name]} {testRun}/>
                    {/if}
                    <button
                        class="nav-link"
                        id="nav-screenshots-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-screenshots-{runId}"
                        type="button"
                        role="tab"
                        ><Fa icon={faImages}/> Screenshots</button
                    >
                    <button
                        class="nav-link"
                        id="nav-resources-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-resources-{runId}"
                        type="button"
                        role="tab"><Fa icon={faCloud}/> Resources</button
                    >
                    <button
                        class="nav-link"
                        id="nav-packages-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-packages-{runId}"
                        type="button"
                        role="tab"><Fa icon={faBox}/> Packages</button
                    >
                    {#if jUnitFetched && jUnitResults.length > 0}
                        <button
                            class="nav-link"
                            id="nav-events-tab-{runId}"
                            data-bs-toggle="tab"
                            data-bs-target="#nav-junit-{runId}"
                            type="button"
                            role="tab"
                            on:click={() => (eventsOpen = true)}
                            ><Fa icon={faClipboard}/> Test Results</button
                        >
                    {/if}
                    <button
                        class="nav-link"
                        id="nav-results-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-results-{runId}"
                        type="button"
                        on:click={() => (resultsOpen = true)}
                        role="tab"
                        ><Fa icon={faTable}/> Results</button
                    >
                    <button
                        class="nav-link"
                        id="nav-events-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-events-{runId}"
                        type="button"
                        role="tab"
                        on:click={() => (eventsOpen = true)}
                        ><Fa icon={faRssSquare}/> Events</button
                    >
                    <button
                        class="nav-link"
                        id="nav-nemesis-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-nemesis-{runId}"
                        type="button"
                        role="tab"><Fa icon={faSpider}/> Nemesis</button
                    >
                    <button
                        class="nav-link"
                        id="nav-logs-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-logs-{runId}"
                        type="button"
                        on:click={() => (artifactTabOpened = true)}
                        role="tab"><Fa icon={faBox}/> Logs</button
                    >
                    <button
                        class="nav-link"
                        id="nav-discuss-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-discuss-{runId}"
                        type="button"
                        on:click={() => (commentsOpen = true)}
                        role="tab"
                        ><Fa icon={faComments}/> Discussion</button
                    >
                    <button
                        class="nav-link"
                        id="nav-issues-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-issues-{runId}"
                        type="button"
                        role="tab"
                        on:click={() => (issuesOpen = true)}
                        ><Fa icon={faCodeBranch}/> Issues</button
                    >
                    <button
                        class="nav-link"
                        id="nav-activity-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-activity-{runId}"
                        type="button"
                        on:click={() => (activityOpen = true)}
                        role="tab"
                        ><Fa icon={faExclamationTriangle}/> Activity</button
                    >
                </div>
            </nav>
            <div
                class="tab-content border-start border-end border-bottom bg-white"
                id="nav-tabContent-{runId}"
            >
                <div
                    class="tab-pane fade show active"
                    id="nav-details-{runId}"
                    role="tabpanel"
                >
                    <TestRunInfo test_run={testRun} release={testInfo.release} group={testInfo.group} test={testInfo.test}/>
                </div>
                {#if testRun.subtest_name && Object.values(Subtests).includes(testRun.subtest_name)}
                    <svelte:component this={SubtestTabBodyComponents[testRun.subtest_name]} {testRun}/>
                {/if}
                <div
                    class="tab-pane fade"
                    id="nav-screenshots-{runId}"
                    role="tabpanel"
                >
                    <Screenshots screenshots={testRun.screenshots} />
                </div>
                <div
                    class="tab-pane fade"
                    id="nav-resources-{runId}"
                    role="tabpanel"
                >
                    <div class="p-2">
                        <ResourcesInfo
                            resources={testRun.allocated_resources}
                        />
                    </div>
                </div>
                <div
                    class="tab-pane fade"
                    id="nav-packages-{runId}"
                    role="tabpanel"
                >
                    <div class="p-2">
                        <PackagesInfo packages={testRun.packages}
                        />
                    </div>
                </div>
                <div class="tab-pane fade" id="nav-junit-{runId}" role="tabpanel">
                   {#if jUnitFetched}
                        <JUnitResults results={jUnitResults}/>
                   {/if}
                </div>
                <div class="tab-pane fade" id="nav-events-{runId}" role="tabpanel">
                    {#if eventsOpen}
                        <EventsTab {testRun} />
                    {/if}
                </div>
                <div
                    class="tab-pane fade"
                    id="nav-nemesis-{runId}"
                    role="tabpanel"
                >
                    <NemesisTable
                        nemesisCollection={testRun.nemesis_data}
                        resources={testRun.allocated_resources}
                    />
                </div>
                <div class="tab-pane fade" id="nav-logs-{runId}" role="tabpanel">
                    {#if artifactTabOpened}
                        <ArtifactTab {testRun} on:refreshRequest={fetchTestRunData}/>
                    {/if}
                </div>
                <div
                    class="tab-pane fade"
                    id="nav-discuss-{runId}"
                    role="tabpanel"
                >
                    {#if commentsOpen}
                        <TestRunComments {testRun} {testInfo}/>
                    {/if}
                </div>
                <div class="tab-pane fade" id="nav-issues-{runId}" role="tabpanel">
                    <IssueTemplate test_run={testRun} test={testInfo.test} />
                    {#if issuesOpen}
                        <IssueTab {testInfo} {runId} />
                    {/if}
                </div>
                <div
                    class="tab-pane fade"
                    id="nav-activity-{runId}"
                    role="tabpanel"
                >
                    {#if activityOpen}
                        <ActivityTab id={runId} />
                    {/if}
                </div>
                <div
                    class="tab-pane fade"
                    id="nav-results-{runId}"
                    role="tabpanel"
                >
                    {#if resultsOpen}
                        <ResultsTab id={runId} test_id={testInfo.test.id} />
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
            <span class="spinner-border me-4" /><span class="fs-4"
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
</style>
