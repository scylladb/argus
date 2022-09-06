    <script>
    import { onMount, onDestroy, createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import {
        faTimes,
        faCheck,
        faSearch,
    } from "@fortawesome/free-solid-svg-icons";
    import humanizeDuration from "humanize-duration";
    import Select from "svelte-select";
    import User from "../Profile/User.svelte";
    import ResourcesInfo from "./ResourcesInfo.svelte";
    import NemesisTable from "./NemesisTable.svelte";
    import ActivityTab from "./ActivityTab.svelte";
    import TestRunInfo from "./TestRunInfo.svelte";
    import Screenshots from "./Screenshots.svelte";
    import TestRunComments from "./TestRunComments.svelte";
    import GithubIssues from "../Github/GithubIssues.svelte";
    import {
        TestStatusChangeable,
        StatusButtonCSSClassMap,
        InProgressStatuses,
        TestInvestigationStatus,
        InvestigationButtonCSSClassMap,
        TestInvestigationStatusStrings,
    } from "../Common/TestStatus";
    import { getPicture } from "../Common/UserUtils";
    import { timestampToISODate } from "../Common/DateUtils";
    import IssueTemplate from "./IssueTemplate.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    import { sendMessage } from "../Stores/AlertStore";
    import { filterUser } from "../Common/SelectUtils";
    import Event from "./Event.svelte";
    import { fetchRun } from "../Common/RunUtils";
    import ArtifactRow from "./ArtifactRow.svelte";
    export let runId = "";
    export let buildNumber = -1;
    export let testInfo = {};
    const dispatch = createEventDispatcher();
    let testRun = undefined;
    let heartbeatHuman = "";
    let newStatus = "";
    let newInvestigationStatus = "";
    let disableButtons = false;
    let currentTime = new Date();
    let clockInterval;
    let runRefreshInterval;
    let users = {};
    let activityOpen = false;
    let commentsOpen = false;
    let issuesOpen = false;
    let artifactTabOpened = false;
    let userSelect = {};
    let failedToLoad = false;

    const investigationStatusIcon = {
        in_progress: faSearch,
        not_investigated: faTimes,
        investigated: faCheck,
    };

    const createUserSelectCollection = function (users) {
        const dummyUser = {
            value: "unassigned",
            label: "unassigned",
            picture_id: undefined,
            full_name: "Unassigned",
            user_id: "none-none-none",
        };

        userSelect = Object.values(users).map((user) => {
            return {
                value: user.username,
                label: user.username,
                picture_id: user.picture_id,
                full_name: user.full_name,
                user_id: user.id,
            };
        });

        return [dummyUser, ...userSelect].reduce((acc, val) => {
            acc[val.user_id] = val;
            return acc;
        }, {});
    };

    $: users = $userList;
    $: userSelect = createUserSelectCollection(users);
    $: heartbeatHuman = humanizeDuration(
        currentTime - testRun?.heartbeat * 1000,
        { round: true }
    );
    $: startedAtHuman = humanizeDuration(
        currentTime - new Date(testRun?.start_time) ,
        { round: true }
    );

    const findAssignee = function (run, userSelect) {
        const placeholder = {
            value: "unassigned",
            id: "none-none-none",
        };
        if (Object.values(userSelect).length < 2) return;
        if (!run) {
            return placeholder;
        }
        if (run.assignee) {
            let user = userSelect[run.assignee];
            if (!user) {
                return placeholder;
            }
            return {
                id: user.user_id,
                value: user.value,
            };
        }
        return placeholder;
    };

    let currentAssignee = "unassigned";
    $: currentAssignee = findAssignee(testRun, userSelect);

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
            disableButtons = false;
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching test run data.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test run data fetch"
                );
            }
        }
    };

    const handleAssign = async function (event) {
        let new_assignee = event.detail.value;
        new_assignee = Object.values(userSelect).find(
            (user) => user.value == new_assignee
        );
        if (!new_assignee) {
            return;
        }
        new_assignee = new_assignee.user_id;
        try {
            let apiResponse = await fetch("/api/v1/test_run/change_assignee", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    test_run_id: runId,
                    assignee: new_assignee,
                }),
            });
            let apiJson = await apiResponse.json();
            console.log(apiJson);
            if (apiJson.status === "ok") {
                fetchTestRunData();
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error assigning person to the test run.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during assignment call"
                );
            }
        }
    };

    const handleStatus = async function () {
        disableButtons = true;
        try {
            let apiResponse = await fetch("/api/v1/test_run/change_status", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    test_run_id: runId,
                    status: newStatus,
                }),
            });
            let apiJson = await apiResponse.json();
            console.log(apiJson);
            if (apiJson.status === "ok") {
                fetchTestRunData();
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error updating test run status.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test run status update"
                );
            }
        }
    };

    const handleInvestigationStatus = async function () {
        disableButtons = true;
        try {
            let apiResponse = await fetch(
                "/api/v1/test_run/change_investigation_status",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        test_run_id: runId,
                        buildId: testRun.build_id,
                        startTime: testRun.start_time,
                        investigation_status: newInvestigationStatus,
                    }),
                }
            );
            let apiJson = await apiResponse.json();
            console.log(apiJson);
            if (apiJson.status === "ok") {
                fetchTestRunData();
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error updating test run investigation status.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test run investigation status update"
                );
            }
        }
    };

    onMount(() => {
        fetchTestRunData();

        runRefreshInterval = setInterval(() => {
            fetchTestRunData();
        }, 1000 * 30);

        clockInterval = setInterval(() => {
            currentTime = new Date();
        }, 1000);
    });

    onDestroy(() => {
        if (clockInterval) clearInterval(clockInterval);
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
                        <div class="dropdown">
                            <button
                                class="btn {StatusButtonCSSClassMap[
                                    testRun.status
                                ]} text-light"
                                type="button"
                                title={timestampToISODate(
                                    testRun.end_time ,
                                    true
                                )}
                                data-bs-toggle="dropdown"
                            >
                                {testRun.status.toUpperCase()}
                                {#if InProgressStatuses.find((status) => status == testRun.status)}
                                    <span
                                        class="spinner-border spinner-border-sm d-inline-block"
                                    />
                                {/if}
                            </button>
                            <ul class="dropdown-menu">
                                {#each Object.keys(TestStatusChangeable) as status}
                                    <li>
                                        <button
                                            class="dropdown-item"
                                            disabled={disableButtons}
                                            on:click={() => {
                                                newStatus =
                                                    status.toLowerCase();
                                                handleStatus();
                                            }}>{status}</button
                                        >
                                    </li>
                                {/each}
                            </ul>
                        </div>
                        <div class="dropdown ms-2">
                            <button
                                class="btn {InvestigationButtonCSSClassMap[
                                    testRun.investigation_status
                                ]} text-light"
                                type="button"
                                data-bs-toggle="dropdown"
                            >
                                <Fa
                                    icon={investigationStatusIcon[
                                        testRun.investigation_status
                                    ]}
                                />
                                {TestInvestigationStatusStrings[
                                    testRun.investigation_status
                                ]}
                            </button>
                            <ul class="dropdown-menu">
                                {#each Object.entries(TestInvestigationStatus) as [key, status]}
                                    <li>
                                        <button
                                            class="dropdown-item"
                                            disabled={disableButtons}
                                            on:click={() => {
                                                newInvestigationStatus = status;
                                                handleInvestigationStatus();
                                            }}
                                            >{TestInvestigationStatusStrings[
                                                status
                                            ]}</button
                                        >
                                    </li>
                                {/each}
                            </ul>
                        </div>
                    </div>
                </div>
                <div class="col-6">
                    <div class="row mb-2 text-sm justify-content-end">
                        <div class="col-6">
                            {#if Object.keys(userSelect).length > 1}
                                <div class="text-muted text-sm text-end mb-2">
                                    Assignee
                                </div>
                                <div class="border rounded">
                                    <div class="d-flex align-items-center m-1">
                                        {#if users[currentAssignee.id]}
                                            <img
                                                class="img-profile me-2"
                                                src={getPicture(
                                                    users[currentAssignee.id]
                                                        ?.picture_id
                                                )}
                                                alt={users[currentAssignee.id]
                                                    ?.username}
                                            />
                                        {/if}
                                        <div class="flex-fill">
                                            <Select
                                                itemFilter={filterUser}
                                                Item={User}
                                                value={currentAssignee.value}
                                                items={Object.values(
                                                    userSelect
                                                )}
                                                hideEmptyState={true}
                                                isClearable={false}
                                                isSearchable={true}
                                                on:select={handleAssign}
                                            />
                                        </div>
                                    </div>
                                </div>
                            {/if}
                        </div>
                    </div>
                    {#if InProgressStatuses.includes(testRun.status)}
                        <div class="row text-end">
                            <div
                                class="col d-flex flex-column text-muted text-sm"
                            >
                                <div>Last heartbeat: {heartbeatHuman} ago</div>
                                <div>Started: {startedAtHuman} ago</div>
                            </div>
                        </div>
                    {/if}
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
                        ><i class="fas fa-info-circle" /> Details</button
                    >
                    <button
                        class="nav-link"
                        id="nav-screenshots-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-screenshots-{runId}"
                        type="button"
                        role="tab"
                        ><i class="fas fa-images" /> Screenshots</button
                    >
                    <button
                        class="nav-link"
                        id="nav-resources-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-resources-{runId}"
                        type="button"
                        role="tab"><i class="fas fa-cloud" /> Resources</button
                    >
                    <button
                        class="nav-link"
                        id="nav-events-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-events-{runId}"
                        type="button"
                        role="tab"
                        ><i class="fas fa-rss-square" /> Events</button
                    >
                    <button
                        class="nav-link"
                        id="nav-nemesis-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-nemesis-{runId}"
                        type="button"
                        role="tab"><i class="fas fa-spider" /> Nemesis</button
                    >
                    <button
                        class="nav-link"
                        id="nav-logs-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-logs-{runId}"
                        type="button"
                        on:click={() => (artifactTabOpened = true)}
                        role="tab"><i class="fas fa-box" /> Logs</button
                    >
                    <button
                        class="nav-link"
                        id="nav-discuss-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-discuss-{runId}"
                        type="button"
                        on:click={() => (commentsOpen = true)}
                        role="tab"
                        ><i class="fas fa-comments" /> Discussion</button
                    >
                    <button
                        class="nav-link"
                        id="nav-issues-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-issues-{runId}"
                        type="button"
                        role="tab"
                        on:click={() => (issuesOpen = true)}
                        ><i class="fas fa-code-branch" /> Issues</button
                    >
                    <button
                        class="nav-link"
                        id="nav-activity-tab-{runId}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-activity-{runId}"
                        type="button"
                        on:click={() => (activityOpen = true)}
                        role="tab"
                        ><i class="fas fa-exclamation-triangle" /> Activity</button
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
                <div class="tab-pane fade" id="nav-events-{runId}" role="tabpanel">
                    <div class="accordion accordion-flush" id="accordionEvents">
                        {#each testRun.events as event_container}
                            <div class="accordion-item">
                                <h2
                                    class="accordion-header"
                                    id="accordionHeadingEvents{event_container.severity}-{runId}"
                                >
                                    <button
                                        class="accordion-button collapsed"
                                        type="button"
                                        data-bs-toggle="collapse"
                                        data-bs-target="#accordionBodyEvents{event_container.severity}-{runId}"
                                    >
                                        {event_container.severity.toUpperCase()}
                                        ({event_container.event_amount})
                                    </button>
                                </h2>
                                <div
                                    id="accordionBodyEvents{event_container.severity}-{runId}"
                                    class="accordion-collapse collapse"
                                    data-bs-parent="#accordionEvents"
                                >
                                    <div class="accordion-body">
                                        {#each event_container.last_events as event}
                                            <Event eventText={event} />
                                        {/each}
                                    </div>
                                </div>
                            </div>
                        {:else}
                            <div class="row">
                                <div class="col text-center p-1 text-muted">
                                    No events submitted yet.
                                </div>
                            </div>
                        {/each}
                    </div>
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
                        {#if testRun.logs.length > 0}
                            <table
                                class="table table-bordered table-sm text-center"
                            >
                                <thead>
                                    <th>Log Type</th>
                                    <th>Log URL</th>
                                </thead>
                                <tbody>
                                    {#each testRun.logs as log}
                                        <ArtifactRow artifactName={log[0]} artifactLink={log[1]}/>
                                    {/each}
                                </tbody>
                            </table>
                        {:else}
                            <div class="row">
                                <div class="col text-center p-1 text-muted">
                                    No logs.
                                </div>
                            </div>
                        {/if}
                    {/if}
                </div>
                <div
                    class="tab-pane fade"
                    id="nav-discuss-{runId}"
                    role="tabpanel"
                >
                    {#if commentsOpen}
                        <TestRunComments id={runId} releaseName={testInfo.release.name} assignee={testRun.assignee} starter={testRun.started_by}/>
                    {/if}
                </div>
                <div class="tab-pane fade" id="nav-issues-{runId}" role="tabpanel">
                    <IssueTemplate test_run={testRun} test={testInfo.test} />
                    {#if issuesOpen}
                        <GithubIssues id={runId} />
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
    .fg-nem-succeeded {
        color: rgb(70, 187, 70);
    }

    .fg-nem-skipped {
        color: rgb(73, 73, 73);
    }

    .fg-nem-failed {
        color: rgb(163, 31, 31);
    }
    .cursor-question {
        cursor: help;
    }

    .img-profile {
        height: 32px;
        border-radius: 50%;
        object-fit: cover;
    }

    .testrun-card {
        background-color: #ededed;
    }

    .top-bar {
        overflow: hidden;
    }
</style>
