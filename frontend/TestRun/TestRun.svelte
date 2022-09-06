    <script>
    import { onMount, onDestroy, createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import {
        faTimes,
        faCheck,
        faSearch,
    } from "@fortawesome/free-solid-svg-icons";
    import { allReleases, allGroups, allTests } from "../Stores/WorkspaceStore";
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
    import {
        polledTestRuns,
        testRunStore,
    } from "../Stores/SingleTestRunSubscriber";
    import { userList } from "../Stores/UserlistSubscriber";
    import { sendMessage } from "../Stores/AlertStore";
    import { filterUser } from "../Common/SelectUtils";
    import Event from "./Event.svelte";
    import ArtifactRow from "./ArtifactRow.svelte";
    export let id = "";
    export let build_number = -1;
    export let testInfo = {};
    const dispatch = createEventDispatcher();
    let test_run = undefined;
    let heartbeatHuman = "";
    let newStatus = "";
    let newInvestigationStatus = "";
    let disableButtons = false;
    let currentTime = new Date();
    let clockInterval;
    let users = {};
    let activityOpen = false;
    let commentsOpen = false;
    let issuesOpen = false;
    let artifactTabOpened = false;
    let userSelect = {};
    let tests;
    let failedToLoad = false;
    $: tests = $allTests;
    let groups;
    $: groups = $allGroups;
    let releases;
    $: releases = $allReleases;

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
        currentTime - test_run?.heartbeat * 1000,
        { round: true }
    );
    $: startedAtHuman = humanizeDuration(
        currentTime - new Date(test_run?.start_time) ,
        { round: true }
    );

    const polledRunUnsub = polledTestRuns.subscribe((data) => {
        test_run = data[id] ?? test_run;
    });

    const findAssignee = function (test_run, userSelect) {
        const placeholder = {
            value: "unassigned",
            id: "none-none-none",
        };
        if (Object.values(userSelect).length < 2) return;
        if (!test_run) {
            return placeholder;
        }
        if (test_run.assignee) {
            let user = userSelect[test_run.assignee];
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
    $: currentAssignee = findAssignee(test_run, userSelect);

    const fetchTestRunData = async function () {
        try {
            let params = new URLSearchParams({
                runId: id,
            }).toString();
            let apiResponse = await fetch('/api/v1/test_run?' + params, {
                method: "GET"
            });
            let apiJson = await apiResponse.json();
            console.log(apiJson);
            if (apiJson.status === "ok") {
                test_run = apiJson.response;
                if (!test_run) {
                    failedToLoad = true;
                    return;
                }
                if (build_number == -1) {
                    build_number = parseInt(
                        test_run.build_job_url.split("/").reverse()[1]
                    );
                }
                testRunStore.update((store) => {
                    if (!store.find((val) => val == id)) {
                        return [...store, id];
                    } else {
                        return store;
                    }
                });
                disableButtons = false;
            } else {
                throw apiJson;
            }
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
                    test_run_id: id,
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
                    test_run_id: id,
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
                        test_run_id: id,
                        buildId: test_run.build_id,
                        startTime: test_run.start_time,
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

        clockInterval = setInterval(() => {
            currentTime = new Date();
        }, 1000);
    });

    onDestroy(() => {
        if (clockInterval) clearInterval(clockInterval);
        polledRunUnsub();
        testRunStore.update((store) => {
            return store.filter((run) => {
                return run != test_run.id;
            });
        });
    });
</script>

<div class="border rounded shadow-sm testrun-card mb-4 top-bar">
    <div class="d-flex px-2 py-2 mb-1 border-bottom bg-white ">
        <div class="p-1">
            {#if test_run}
                <a class="link-dark" href="/test/{test_run.test_id}/runs?additionalRuns[]={test_run.id}">
                    {test_run.build_id}#{build_number}
                </a>
            {/if}
        </div>
        <div class="ms-auto text-end">
            <button class="btn btn-sm btn-outline-dark" title="Close" on:click={() => {
                dispatch("closeRun", { id: id })
            }}
                ><Fa icon={faTimes} /></button
            >
        </div>
    </div>
    {#if test_run}
        <div class="p-2">
            <div class="row p-2">
                <div class="col-6">
                    <div class="d-flex align-items-center">
                        <div class="dropdown">
                            <button
                                class="btn {StatusButtonCSSClassMap[
                                    test_run.status
                                ]} text-light"
                                type="button"
                                title={timestampToISODate(
                                    test_run.end_time ,
                                    true
                                )}
                                data-bs-toggle="dropdown"
                            >
                                {test_run.status.toUpperCase()}
                                {#if InProgressStatuses.find((status) => status == test_run.status)}
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
                                    test_run.investigation_status
                                ]} text-light"
                                type="button"
                                data-bs-toggle="dropdown"
                            >
                                <Fa
                                    icon={investigationStatusIcon[
                                        test_run.investigation_status
                                    ]}
                                />
                                {TestInvestigationStatusStrings[
                                    test_run.investigation_status
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
                    {#if InProgressStatuses.includes(test_run.status)}
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
                <div class="nav nav-tabs" id="nav-tab-{id}" role="tablist">
                    <button
                        class="nav-link active"
                        id="nav-details-tab-{id}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-details-{id}"
                        type="button"
                        role="tab"
                        ><i class="fas fa-info-circle" /> Details</button
                    >
                    <button
                        class="nav-link"
                        id="nav-screenshots-tab-{id}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-screenshots-{id}"
                        type="button"
                        role="tab"
                        ><i class="fas fa-images" /> Screenshots</button
                    >
                    <button
                        class="nav-link"
                        id="nav-resources-tab-{id}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-resources-{id}"
                        type="button"
                        role="tab"><i class="fas fa-cloud" /> Resources</button
                    >
                    <button
                        class="nav-link"
                        id="nav-events-tab-{id}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-events-{id}"
                        type="button"
                        role="tab"
                        ><i class="fas fa-rss-square" /> Events</button
                    >
                    <button
                        class="nav-link"
                        id="nav-nemesis-tab-{id}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-nemesis-{id}"
                        type="button"
                        role="tab"><i class="fas fa-spider" /> Nemesis</button
                    >
                    <button
                        class="nav-link"
                        id="nav-logs-tab-{id}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-logs-{id}"
                        type="button"
                        on:click={() => (artifactTabOpened = true)}
                        role="tab"><i class="fas fa-box" /> Logs</button
                    >
                    <button
                        class="nav-link"
                        id="nav-discuss-tab-{id}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-discuss-{id}"
                        type="button"
                        on:click={() => (commentsOpen = true)}
                        role="tab"
                        ><i class="fas fa-comments" /> Discussion</button
                    >
                    <button
                        class="nav-link"
                        id="nav-issues-tab-{id}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-issues-{id}"
                        type="button"
                        role="tab"
                        on:click={() => (issuesOpen = true)}
                        ><i class="fas fa-code-branch" /> Issues</button
                    >
                    <button
                        class="nav-link"
                        id="nav-activity-tab-{id}"
                        data-bs-toggle="tab"
                        data-bs-target="#nav-activity-{id}"
                        type="button"
                        on:click={() => (activityOpen = true)}
                        role="tab"
                        ><i class="fas fa-exclamation-triangle" /> Activity</button
                    >
                </div>
            </nav>
            <div
                class="tab-content border-start border-end border-bottom bg-white"
                id="nav-tabContent-{id}"
            >
                <div
                    class="tab-pane fade show active"
                    id="nav-details-{id}"
                    role="tabpanel"
                >
                    <TestRunInfo {test_run} release={testInfo.release} group={testInfo.group} test={testInfo.test}/>
                </div>
                <div
                    class="tab-pane fade"
                    id="nav-screenshots-{id}"
                    role="tabpanel"
                >
                    <Screenshots screenshots={test_run.screenshots} />
                </div>
                <div
                    class="tab-pane fade"
                    id="nav-resources-{id}"
                    role="tabpanel"
                >
                    <div class="p-2">
                        <ResourcesInfo
                            resources={test_run.allocated_resources}
                        />
                    </div>
                </div>
                <div class="tab-pane fade" id="nav-events-{id}" role="tabpanel">
                    <div class="accordion accordion-flush" id="accordionEvents">
                        {#each test_run.events as event_container}
                            <div class="accordion-item">
                                <h2
                                    class="accordion-header"
                                    id="accordionHeadingEvents{event_container.severity}-{id}"
                                >
                                    <button
                                        class="accordion-button collapsed"
                                        type="button"
                                        data-bs-toggle="collapse"
                                        data-bs-target="#accordionBodyEvents{event_container.severity}-{id}"
                                    >
                                        {event_container.severity.toUpperCase()}
                                        ({event_container.event_amount})
                                    </button>
                                </h2>
                                <div
                                    id="accordionBodyEvents{event_container.severity}-{id}"
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
                    id="nav-nemesis-{id}"
                    role="tabpanel"
                >
                    <NemesisTable
                        nemesisCollection={test_run.nemesis_data}
                        resources={test_run.allocated_resources}
                    />
                </div>
                <div class="tab-pane fade" id="nav-logs-{id}" role="tabpanel">
                    {#if artifactTabOpened}
                        {#if test_run.logs.length > 0}
                            <table
                                class="table table-bordered table-sm text-center"
                            >
                                <thead>
                                    <th>Log Type</th>
                                    <th>Log URL</th>
                                </thead>
                                <tbody>
                                    {#each test_run.logs as log}
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
                    id="nav-discuss-{id}"
                    role="tabpanel"
                >
                    {#if commentsOpen}
                        <TestRunComments {id} releaseName={testInfo.release.name} assignee={test_run.assignee} starter={test_run.started_by}/>
                    {/if}
                </div>
                <div class="tab-pane fade" id="nav-issues-{id}" role="tabpanel">
                    <IssueTemplate {test_run} test={testInfo.test} />
                    {#if issuesOpen}
                        <GithubIssues {id} />
                    {/if}
                </div>
                <div
                    class="tab-pane fade"
                    id="nav-activity-{id}"
                    role="tabpanel"
                >
                    {#if activityOpen}
                        <ActivityTab {id} />
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
