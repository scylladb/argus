<script lang="ts" module>
    interface CloudNodesInfo {
        image_id: string,
        instance_type: string,
        node_amount: string,
        post_behaviour: string,
    }

    interface CloudResource {
        name: string,
        state: string,
        resource_type: string,
        instance_info: {
            provider: string,
            region: string,
            public_ip: string,
            private_ip: string,
            dc_name: string,
            rack_name: string,
            creation_time: string,
            termination_time: string,
            termination_reason: string,
            shards_amount: number,
        }
    }

    interface SCTPackage {
        name: string,
        version: string,
        date: string,
        revision_id: string,
        build_id: string,
    }

    export interface NemesisInfo {
        class_name: string,
        name: string,
        duration: number,
        target_node: {
            name: string,
            ip: string,
            shards: number
        }
        status: string,
        start_time: number,
        end_time: number,
        stack_trace: string,
    }

    interface JUnitReport {
        file_name: string,
        report: string,
    }

    export interface TestInfo {
        release: {
            id: string,
            name: string,
        },
        test: {
            id: string,
            pretty_name: string,
            name: string,
            plugin_name: string,
        },
        group: {
            id: string,
            pretty_name: string,
            name: string,
        },
    }

    export interface SCTTestRun {
        id: string,
        build_id: string,
        assignee: string,
        start_time: string,
        end_time: string,
        build_job_url: string,
        subtest_name: string,
        status: string,
        test_id: string,
        release_id: string,
        group_id: string,
        investigation_status: string,
        screenshots: string[],
        packages: SCTPackage[],
        allocated_resources: CloudResource[],
        nemesis_data: NemesisInfo[],
        cloud_setup: {
            backend: string,
            db_node: CloudNodesInfo,
            loader_node: CloudNodesInfo,
            monitor_node: CloudNodesInfo,
        }
    }

    export interface StressCommand {
        cmd: string,
        ts: string,
        loader_name: string,
        log_name: string,
    }

    export interface SCTTestRunResponse {
        status: string,
        response: SCTTestRun,
    }

    export interface APIError {
        status: string
        response: {
            arguments: string[],
            exception: string,
            trace_id: string,
        }
    }
</script>

<script lang="ts">
    import { onMount, createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import {
        faBox,
        faChartSimple,
        faClipboard,
        faCloud,
        faCodeBranch,
        faComments,
        faExclamationTriangle,
        faEye,
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
    import RunStatusButton from "./RunStatusButton.svelte";
    import RunInvestigationStatusButton from "./RunInvestigationStatusButton.svelte";
    import RunAssigneeSelector from "./RunAssigneeSelector.svelte";
    import HeartbeatIndicator from "./HeartbeatIndicator.svelte";
    import EventsTab from "./EventsTab.svelte";
    import ArtifactTab from "./ArtifactTab.svelte";
    import IssueTab, { submitIssue } from "./IssueTab.svelte";
    import { SubtestTabBodyComponents, SubtestTabMeta, Subtests } from "./SCTSubTests/Subtest";
    import PackagesInfo from "./PackagesInfo.svelte";
    import JUnitResults from "./jUnitResults.svelte";
    import ResultsTab from "./ResultsTab.svelte";
    import SctEvents from "./SCT/SctEvents.svelte";
    import SctSetup from "./SCT/SctSetup.svelte";
    import SctConfig from "./SCT/SctConfig.svelte";

    interface Props {
        runId?: string;
        buildNumber?: any;
        testInfo: TestInfo;
        tab?: string;
    }

    let {
        runId = "",
        buildNumber = $bindable(-1),
        testInfo,
        tab = ""
    }: Props = $props();


    const dispatch = createEventDispatcher();

    let testRun: SCTTestRun | undefined = $state();
    let runRefreshInterval: ReturnType<typeof setInterval>;
    let activeTab: string = $state(tab.toLowerCase() || "details");
    let failedToLoad = $state(false);
    let jUnitFetched = $state(false);
    let jUnitResults: JUnitReport[] = $state([]);

    // Track which tabs have been visited
    let visitedTabs: Record<string, boolean> = $state({});
    visitedTabs[activeTab] = true;

    const fetchTestRunData = async function () {
        try {
            let res = await fetch(`/api/v1/run/${testInfo.test.plugin_name}/${runId}`);
            if (res.status != 200) {
                throw new Error(`Network error: ${res.status}`);
            }
            let json = await res.json();
            if (json.status != "ok") {
                throw json.response;
            }
            testRun = json.response;
            if (!testRun) {
                failedToLoad = true;
                return;
            }
            if (buildNumber == -1) {
                buildNumber = parseInt(testRun.build_job_url.split("/").reverse()[1]);
            }
            jUnitResults = json.response.junit_reports ?? [];
            jUnitFetched = true;
        } catch (error) {
            if ((error as APIError)?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching test run data.\nMessage: ${(error as APIError).response.arguments[0]}`,
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

    const setActiveTab = (tabName: string) => {
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

    onMount(() => {
        fetchTestRunData();
        runRefreshInterval = setInterval(fetchTestRunData, 120_000);
        return () => {
            if (runRefreshInterval) clearInterval(runRefreshInterval);
        };
    });
</script>

<div class="border rounded shadow-sm testrun-card mb-4 top-bar">
    <div class="d-flex px-2 py-2 mb-1 border-bottom bg-white">
        <div class="p-1">
            {#if testRun}
                <a class="link-dark" href="/tests/{testInfo.test.plugin_name}/{testRun.id}">
                    {testRun.build_id}#{buildNumber}
                </a>
            {/if}
        </div>
        <div class="ms-auto text-end">
            <button
                class="btn btn-sm btn-outline-dark"
                title="Refresh"
                onclick={() => {
                    fetchTestRunData();
                }}><Fa icon={faRefresh} /></button
            >
        </div>
        <div class="ms-2 text-end">
            <button
                class="btn btn-sm btn-outline-dark"
                title="Close"
                onclick={() => dispatch("closeRun", { id: runId })}
            >
                <Fa icon={faTimes} />
            </button>
        </div>
    </div>
    {#if testRun}
        <div class="p-2">
            <div class="row p-2">
                <div class="col-6">
                    <div class="d-flex align-items-center">
                        <RunStatusButton
                            {testRun}
                            on:statusUpdate={(e) => {
                                if (!testRun) return;
                                testRun.status = e.detail.status;
                                dispatch("runStatusChange");
                            }}
                        />
                        <RunInvestigationStatusButton
                            {testRun}
                            on:investigationStatusChange={(e) => {
                                if (!testRun) return;
                                testRun.investigation_status = e.detail.status;
                                dispatch("investigationStatusChange", e.detail);
                            }}
                        />
                    </div>
                </div>
                <div class="col-6">
                    <RunAssigneeSelector
                        {testRun}
                        on:assigneeUpdate={(e) => {
                            if (!testRun) return;
                            testRun.assignee = e.detail.assignee;
                        }}
                    />
                    <HeartbeatIndicator {testRun} />
                </div>
            </div>
            <div class="argus-tab-bar" role="tablist">
                    <button class="argus-tab" class:active={activeTab === "details"} type="button" role="tab" onclick={() => setActiveTab("details")}>
                        <Fa icon={faInfoCircle} /> Details
                    </button>
                    <button class="argus-tab" class:active={activeTab === "setup"} type="button" role="tab" onclick={() => setActiveTab("setup")}>
                        <Fa icon={faCodeBranch} /> SCT Runtime
                    </button>
                    {#if testRun.subtest_name && Object.values(Subtests).includes(testRun.subtest_name)}
                        {@const meta = SubtestTabMeta[testRun.subtest_name]}
                        <button class="argus-tab" class:active={activeTab === meta.key} type="button" role="tab" onclick={() => setActiveTab(meta.key)}>
                            <Fa icon={meta.faIcon === "faChartSimple" ? faChartSimple : faEye} /> {meta.label}
                        </button>
                    {/if}
                    <button class="argus-tab" class:active={activeTab === "screenshots"} type="button" role="tab" onclick={() => setActiveTab("screenshots")}>
                        <Fa icon={faImages} /> Screenshots
                    </button>
                    <button class="argus-tab" class:active={activeTab === "resources"} type="button" role="tab" onclick={() => setActiveTab("resources")}>
                        <Fa icon={faCloud} /> Resources
                    </button>
                    <button class="argus-tab" class:active={activeTab === "packages"} type="button" role="tab" onclick={() => setActiveTab("packages")}>
                        <Fa icon={faCodeBranch} /> Packages
                    </button>
                    {#if jUnitFetched && jUnitResults.length > 0}
                        <button class="argus-tab" class:active={activeTab === "junit"} type="button" role="tab" onclick={() => setActiveTab("junit")}>
                            <Fa icon={faClipboard} /> Test Results
                        </button>
                    {/if}
                    <button class="argus-tab" class:active={activeTab === "results"} type="button" role="tab" onclick={() => setActiveTab("results")}>
                        <Fa icon={faTable} /> Results
                    </button>
                    <button class="argus-tab" class:active={activeTab === "events"} type="button" role="tab" onclick={() => setActiveTab("events")}>
                        <Fa icon={faRssSquare} /> Events
                    </button>
                    <button class="argus-tab" class:active={activeTab === "nemesis"} type="button" role="tab" onclick={() => setActiveTab("nemesis")}>
                        <Fa icon={faSpider} /> Nemesis
                    </button>
                    <button class="argus-tab" class:active={activeTab === "logs"} type="button" role="tab" onclick={() => setActiveTab("logs")}>
                        <Fa icon={faBox} /> Logs
                    </button>
                    <button class="argus-tab" class:active={activeTab === "discuss"} type="button" role="tab" onclick={() => setActiveTab("discuss")}>
                        <Fa icon={faComments} /> Discussion
                    </button>
                    <button class="argus-tab" class:active={activeTab === "issues"} type="button" role="tab" onclick={() => setActiveTab("issues")}>
                        <Fa icon={faCodeBranch} /> Issues
                    </button>
                    <button class="argus-tab" class:active={activeTab === "activity"} type="button" role="tab" onclick={() => setActiveTab("activity")}>
                        <Fa icon={faExclamationTriangle} /> Activity
                    </button>
                    <button class="argus-tab" class:active={activeTab === "sct-events"} type="button" role="tab" onclick={() => setActiveTab("sct-events")}>
                        <Fa icon={faRssSquare} /> Events (Experimental)
                    </button>
                </div>
                <div class="argus-tab-select">
                    <select onchange={(e) => setActiveTab(e.currentTarget.value)} value={activeTab}>
                        <option value="details">Details</option>
                        <option value="setup">SCT Runtime</option>
                        {#if testRun.subtest_name && Object.values(Subtests).includes(testRun.subtest_name)}
                            {@const meta = SubtestTabMeta[testRun.subtest_name]}
                            <option value={meta.key}>{meta.label}</option>
                        {/if}
                        <option value="screenshots">Screenshots</option>
                        <option value="resources">Resources</option>
                        <option value="packages">Packages</option>
                        {#if jUnitFetched && jUnitResults.length > 0}
                            <option value="junit">Test Results</option>
                        {/if}
                        <option value="results">Results</option>
                        <option value="events">Events</option>
                        <option value="nemesis">Nemesis</option>
                        <option value="logs">Logs</option>
                        <option value="discuss">Discussion</option>
                        <option value="issues">Issues</option>
                        <option value="activity">Activity</option>
                        <option value="sct-events">Events (Experimental)</option>
                    </select>
                </div>
            <div class="argus-tab-content" id="nav-tabContent-{runId}">
                <div role="tabpanel" style:display={activeTab === "details" ? "block" : "none"}>
                    <TestRunInfo
                        test_run={testRun}
                        release={testInfo.release}
                        group={testInfo.group}
                        test={testInfo.test}
                        on:cloneComplete
                    />
                </div>
                <div role="tabpanel" style:display={activeTab === "setup" ? "block" : "none"}>
                    {#if visitedTabs["setup"]}
                        <SctSetup {testRun} />
                        <SctConfig {testRun} />
                    {/if}
                </div>
                {#if testRun.subtest_name && Object.values(Subtests).includes(testRun.subtest_name)}
                    {@const SubtestComponent = SubtestTabBodyComponents[testRun.subtest_name]}
                    {@const meta = SubtestTabMeta[testRun.subtest_name]}
                    <div role="tabpanel" style:display={activeTab === meta.key ? "block" : "none"}>
                        <SubtestComponent {testRun} />
                    </div>
                {/if}
                <div role="tabpanel" style:display={activeTab === "screenshots" ? "block" : "none"}>
                    <Screenshots {testInfo} runId={testRun.id} screenshots={testRun.screenshots} />
                </div>
                <div role="tabpanel" style:display={activeTab === "resources" ? "block" : "none"}>
                    <div class="p-2 overflow-scroll">
                        <ResourcesInfo
                            resources={testRun.allocated_resources}
                            backend={testRun.cloud_setup?.backend}
                            run_id={testRun.id}
                        />
                    </div>
                </div>
                <div role="tabpanel" style:display={activeTab === "packages" ? "block" : "none"}>
                    <div class="p-2 overflow-scroll">
                        <PackagesInfo packages={testRun.packages} />
                    </div>
                </div>
                <div class="overflow-scroll" role="tabpanel" style:display={activeTab === "junit" ? "block" : "none"}>
                    {#if jUnitFetched}
                        <JUnitResults results={jUnitResults} />
                    {/if}
                </div>
                <div role="tabpanel" style:display={activeTab === "results" ? "block" : "none"}>
                    {#if visitedTabs["results"]}
                        <ResultsTab id={runId} test_id={testInfo.test.id} />
                    {/if}
                </div>
                <div role="tabpanel" style:display={activeTab === "events" ? "block" : "none"}>
                    {#if visitedTabs["events"]}
                        <EventsTab {testRun} on:issueAttach={(e) => submitIssue(e.detail.url, runId, testInfo.test.id)} />
                    {/if}
                </div>
                <div role="tabpanel" style:display={activeTab === "sct-events" ? "block" : "none"}>
                    {#if visitedTabs["sct-events"]}
                        <SctEvents {testRun} nemeses={testRun.nemesis_data} issueAttach={(url) => submitIssue(url, runId, testInfo.test.id)}/>
                    {/if}
                </div>
                <div class="overflow-scroll" role="tabpanel" style:display={activeTab === "nemesis" ? "block" : "none"}>
                    <NemesisTable nemesisCollection={testRun.nemesis_data} resources={testRun.allocated_resources} />
                </div>
                <div class="overflow-scroll" role="tabpanel" style:display={activeTab === "logs" ? "block" : "none"}>
                    {#if visitedTabs["logs"]}
                        <ArtifactTab {testRun} {testInfo} on:refreshRequest={fetchTestRunData} />
                    {/if}
                </div>
                <div role="tabpanel" style:display={activeTab === "discuss" ? "block" : "none"}>
                    {#if visitedTabs["discuss"]}
                        <TestRunComments {testRun} {testInfo} />
                    {/if}
                </div>
                <div role="tabpanel" style:display={activeTab === "issues" ? "block" : "none"}>
                    <IssueTemplate test_run={testRun} test={testInfo.test} />
                    {#if visitedTabs["issues"]}
                        <IssueTab {testInfo} {runId} />
                    {/if}
                </div>
                <div role="tabpanel" style:display={activeTab === "activity" ? "block" : "none"}>
                    {#if visitedTabs["activity"]}
                        <ActivityTab id={runId} />
                    {/if}
                </div>
            </div>
        </div>
    {:else if failedToLoad}
        <div class="text-center p-2 m-1 d-flex align-items-center justify-content-center">
            <span class="fs-4">Run not found.</span>
        </div>
    {:else}
        <div class="text-center p-2 m-1 d-flex align-items-center justify-content-center">
            <span class="spinner-border me-4"></span><span class="fs-4">Loading...</span>
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
    @media (prefers-color-scheme: dark) {
        .testrun-card {
            background-color: #2b3035;
        }
    }
</style>
