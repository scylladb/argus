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
    import IssueTab, { submitIssue } from "./IssueTab.svelte";
    import { SubtestTabBodyComponents, SubtestTabComponents, Subtests } from "./SCTSubTests/Subtest";
    import PackagesInfo from "./PackagesInfo.svelte";
    import JUnitResults from "./jUnitResults.svelte";
    import ResultsTab from "./ResultsTab.svelte";
    import SctEvents from "./SCT/SctEvents.svelte";

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
            let run: SCTTestRun = await fetchRun(testInfo.test.plugin_name, runId);
            testRun = run;
            if (!testRun) {
                failedToLoad = true;
                return;
            }
            if (buildNumber == -1) {
                buildNumber = parseInt(testRun.build_job_url.split("/").reverse()[1]);
            }
            fetchJunitReports();
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

    const fetchJunitReports = async function () {
        try {
            let res = await fetch(`/api/v1/client/sct/${testRun?.id}/junit/get_all`);
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
            if ((error as APIError)?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching test run junit results data.\nMessage: ${(error as APIError).response.arguments[0]}`,
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
        runRefreshInterval = setInterval(fetchTestRunData, 30_000);
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
            <nav>
                <div class="nav nav-tabs" id="nav-tab-{runId}" role="tablist">
                    <button
                        class="nav-link"
                        class:active={activeTab === "details"}
                        id="nav-details-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-details-{runId}"
                        type="button"
                        role="tab"
                        onclick={() => setActiveTab("details")}
                        onkeydown={(e) => e.key === "Enter" && setActiveTab("details")}
                    >
                        <Fa icon={faInfoCircle} /> Details
                    </button>
                    {#if testRun.subtest_name && Object.values(Subtests).includes(testRun.subtest_name)}
                        {@const SvelteComponent = SubtestTabComponents[testRun.subtest_name]}
                        <SvelteComponent {testRun} />
                    {/if}
                    <button
                        class="nav-link"
                        class:active={activeTab === "screenshots"}
                        id="nav-screenshots-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-screenshots-{runId}"
                        type="button"
                        role="tab"
                        onclick={() => setActiveTab("screenshots")}
                        onkeydown={(e) => e.key === "Enter" && setActiveTab("screenshots")}
                    >
                        <Fa icon={faImages} /> Screenshots
                    </button>
                    <button
                        class="nav-link"
                        class:active={activeTab === "resources"}
                        id="nav-resources-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-resources-{runId}"
                        type="button"
                        role="tab"
                        onclick={() => setActiveTab("resources")}
                        onkeydown={(e) => e.key === "Enter" && setActiveTab("resources")}
                    >
                        <Fa icon={faCloud} /> Resources
                    </button>
                    <button
                        class="nav-link"
                        class:active={activeTab === "packages"}
                        id="nav-packages-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-packages-{runId}"
                        type="button"
                        role="tab"
                        onclick={() => setActiveTab("packages")}
                        onkeydown={(e) => e.key === "Enter" && setActiveTab("packages")}
                    >
                        <Fa icon={faCodeBranch} /> Packages
                    </button>
                    {#if jUnitFetched && jUnitResults.length > 0}
                        <button
                            class="nav-link"
                            class:active={activeTab === "junit"}
                            id="nav-junit-tab-{runId}"
                            data-bs-toggle="tab"
                            data-bs-target="#nav-junit-{runId}"
                            type="button"
                            role="tab"
                            onclick={() => setActiveTab("junit")}
                            onkeydown={(e) => e.key === "Enter" && setActiveTab("junit")}
                        >
                            <Fa icon={faClipboard} /> Test Results
                        </button>
                    {/if}
                    <button
                        class="nav-link"
                        class:active={activeTab === "results"}
                        id="nav-results-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-results-{runId}"
                        type="button"
                        role="tab"
                        onclick={() => setActiveTab("results")}
                        onkeydown={(e) => e.key === "Enter" && setActiveTab("results")}
                    >
                        <Fa icon={faTable} /> Results
                    </button>
                    <button
                        class="nav-link"
                        class:active={activeTab === "events"}
                        id="nav-events-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-events-{runId}"
                        type="button"
                        role="tab"
                        onclick={() => setActiveTab("events")}
                        onkeydown={(e) => e.key === "Enter" && setActiveTab("events")}
                    >
                        <Fa icon={faRssSquare} /> Events
                    </button>
                    <button
                        class="nav-link"
                        class:active={activeTab === "nemesis"}
                        id="nav-nemesis-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-nemesis-{runId}"
                        type="button"
                        role="tab"
                        onclick={() => setActiveTab("nemesis")}
                        onkeydown={(e) => e.key === "Enter" && setActiveTab("nemesis")}
                    >
                        <Fa icon={faSpider} /> Nemesis
                    </button>
                    <button
                        class="nav-link"
                        class:active={activeTab === "logs"}
                        id="nav-logs-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-logs-{runId}"
                        type="button"
                        role="tab"
                        onclick={() => setActiveTab("logs")}
                        onkeydown={(e) => e.key === "Enter" && setActiveTab("logs")}
                    >
                        <Fa icon={faBox} /> Logs
                    </button>
                    <button
                        class="nav-link"
                        class:active={activeTab === "discuss"}
                        id="nav-discuss-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-discuss-{runId}"
                        type="button"
                        role="tab"
                        onclick={() => setActiveTab("discuss")}
                        onkeydown={(e) => e.key === "Enter" && setActiveTab("discuss")}
                    >
                        <Fa icon={faComments} /> Discussion
                    </button>
                    <button
                        class="nav-link"
                        class:active={activeTab === "issues"}
                        id="nav-issues-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-issues-{runId}"
                        type="button"
                        role="tab"
                        onclick={() => setActiveTab("issues")}
                        onkeydown={(e) => e.key === "Enter" && setActiveTab("issues")}
                    >
                        <Fa icon={faCodeBranch} /> Issues
                    </button>
                    <button
                        class="nav-link"
                        class:active={activeTab === "activity"}
                        id="nav-activity-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-activity-{runId}"
                        type="button"
                        role="tab"
                        onclick={() => setActiveTab("activity")}
                        onkeydown={(e) => e.key === "Enter" && setActiveTab("activity")}
                    >
                        <Fa icon={faExclamationTriangle} /> Activity
                    </button>
                    <button
                        class="nav-link"
                        class:active={activeTab === "sct-events"}
                        id="nav-sct-events-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-sct-events-{runId}"
                        type="button"
                        role="tab"
                        onclick={() => setActiveTab("sct-events")}
                        onkeydown={(e) => e.key === "Enter" && setActiveTab("sct-events")}
                    >
                        <Fa icon={faRssSquare} /> Events (Experimental)
                    </button>
                </div>
            </nav>
            <div class="tab-content border-start border-end border-bottom bg-white" id="nav-tabContent-{runId}">
                <div
                    class="tab-pane fade"
                    class:show={activeTab === "details"}
                    class:active={activeTab === "details"}
                    id="nav-details-{runId}"
                    role="tabpanel"
                >
                    <TestRunInfo
                        test_run={testRun}
                        release={testInfo.release}
                        group={testInfo.group}
                        test={testInfo.test}
                        on:cloneComplete
                    />
                </div>
                {#if testRun.subtest_name && Object.values(Subtests).includes(testRun.subtest_name)}
                    {@const SubtestComponent = SubtestTabBodyComponents[testRun.subtest_name]}
                    <SubtestComponent {testRun} />
                {/if}
                <div
                    class="tab-pane fade"
                    class:show={activeTab === "screenshots"}
                    class:active={activeTab === "screenshots"}
                    id="nav-screenshots-{runId}"
                    role="tabpanel"
                >
                    <Screenshots {testInfo} runId={testRun.id} screenshots={testRun.screenshots} />
                </div>
                <div
                    class="tab-pane fade"
                    class:show={activeTab === "resources"}
                    class:active={activeTab === "resources"}
                    id="nav-resources-{runId}"
                    role="tabpanel"
                >
                    <div class="p-2 overflow-scroll">
                        <ResourcesInfo
                            resources={testRun.allocated_resources}
                            backend={testRun.cloud_setup?.backend}
                            run_id={testRun.id}
                        />
                    </div>
                </div>
                <div
                    class="tab-pane fade"
                    class:show={activeTab === "packages"}
                    class:active={activeTab === "packages"}
                    id="nav-packages-{runId}"
                    role="tabpanel"
                >
                    <div class="p-2 overflow-scroll">
                        <PackagesInfo packages={testRun.packages} />
                    </div>
                </div>
                <div
                    class="tab-pane fade overflow-scroll"
                    class:show={activeTab === "junit"}
                    class:active={activeTab === "junit"}
                    id="nav-junit-{runId}"
                    role="tabpanel"
                >
                    {#if jUnitFetched}
                        <JUnitResults results={jUnitResults} />
                    {/if}
                </div>
                <div
                    class="tab-pane fade"
                    class:show={activeTab === "results"}
                    class:active={activeTab === "results"}
                    id="nav-results-{runId}"
                    role="tabpanel"
                >
                    {#if visitedTabs["results"]}
                        <ResultsTab id={runId} test_id={testInfo.test.id} />
                    {/if}
                </div>
                <div
                    class="tab-pane fade"
                    class:show={activeTab === "events"}
                    class:active={activeTab === "events"}
                    id="nav-events-{runId}"
                    role="tabpanel"
                >
                    {#if visitedTabs["events"]}
                        <EventsTab {testRun} on:issueAttach={(e) => submitIssue(e.detail.url, runId, testInfo.test.id)} />
                    {/if}
                </div>
                <div
                    class="tab-pane fade"
                    class:show={activeTab === "sct-events"}
                    class:active={activeTab === "sct-events"}
                    id="nav-sct-events-{runId}"
                    role="tabpanel"
                >
                    {#if visitedTabs["sct-events"]}
                        <SctEvents {testRun} nemeses={testRun.nemesis_data} />
                    {/if}
                </div>
                <div
                    class="tab-pane fade overflow-scroll"
                    class:show={activeTab === "nemesis"}
                    class:active={activeTab === "nemesis"}
                    id="nav-nemesis-{runId}"
                    role="tabpanel"
                >
                    <NemesisTable nemesisCollection={testRun.nemesis_data} resources={testRun.allocated_resources} />
                </div>
                <div
                    class="tab-pane fade overflow-scroll"
                    class:show={activeTab === "logs"}
                    class:active={activeTab === "logs"}
                    id="nav-logs-{runId}"
                    role="tabpanel"
                >
                    {#if visitedTabs["logs"]}
                        <ArtifactTab {testRun} {testInfo} on:refreshRequest={fetchTestRunData} />
                    {/if}
                </div>
                <div
                    class="tab-pane fade"
                    class:show={activeTab === "discuss"}
                    class:active={activeTab === "discuss"}
                    id="nav-discuss-{runId}"
                    role="tabpanel"
                >
                    {#if visitedTabs["discuss"]}
                        <TestRunComments {testRun} {testInfo} />
                    {/if}
                </div>
                <div
                    class="tab-pane fade"
                    class:show={activeTab === "issues"}
                    class:active={activeTab === "issues"}
                    id="nav-issues-{runId}"
                    role="tabpanel"
                >
                    <IssueTemplate test_run={testRun} test={testInfo.test} />
                    {#if visitedTabs["issues"]}
                        <IssueTab {testInfo} {runId} />
                    {/if}
                </div>
                <div
                    class="tab-pane fade"
                    class:show={activeTab === "activity"}
                    class:active={activeTab === "activity"}
                    id="nav-activity-{runId}"
                    role="tabpanel"
                >
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
</style>
