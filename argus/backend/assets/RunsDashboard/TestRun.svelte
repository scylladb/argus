<script>
    import { onMount, onDestroy } from "svelte";
    import humanizeDuration from "humanize-duration";
    import Select from "svelte-select";
    import User from "./User.svelte";
    import ResourcesInfo from "./ResourcesInfo.svelte";
    import NemesisData from "./NemesisData.svelte";
    import ActivityTab from "./ActivityTab.svelte";
    import TestRunInfo from "./TestRunInfo.svelte";
    import TestRunComments from "./TestRunComments.svelte";
    import GithubIssues from "./GithubIssues.svelte";
    import {
        TestStatusChangeable,
        StatusButtonCSSClassMap,
        InProgressStatuses,
    } from "./TestStatus.js";
    import IssueTemplate from "./IssueTemplate.svelte";
    import { polledTestRuns, testRunStore } from "./SingleTestRunSubscriber.js";
    import { userList } from "./UserlistSubscriber.js";
    import { sendMessage } from "./AlertStore";
    export let id = "";
    export let build_number = -1;
    let test_run = undefined;
    let heartbeatHuman = "";
    let newStatus = "";
    let disableButtons = false;
    let currentTime = new Date();
    let clockInterval;
    let users = {};
    let activityOpen = false;
    let commentsOpen = false;
    let issuesOpen = false;
    let userSelect = [];

    const createUserSelectCollection = function (users) {
        const dummyUser = {
            value: "NONE",
            label: "nobody",
            picture_id: undefined,
            full_name: "Nobody",
        };
        userSelect = Object.keys(users).map((user) => {
            return {
                value: users[user].id,
                label: users[user].username,
                picture_id: users[user].picture_id,
                full_name: users[user].full_name,
            };
        });
        return [dummyUser, ...userSelect];
    };

    $: users = $userList;
    $: userSelect = createUserSelectCollection(users);
    $: heartbeatHuman = humanizeDuration(
        currentTime - test_run?.heartbeat * 1000,
        { round: true }
    );

    $: startedAtHuman = humanizeDuration(
        currentTime - test_run?.start_time * 1000,
        { round: true }
    );

    polledTestRuns.subscribe((data) => {
        test_run = data[id] ?? test_run;
    });

    const fetchTestRunData = async function () {
        try {
            let apiResponse = await fetch("/api/v1/test_run", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    test_id: id,
                }),
            });
            let apiJson = await apiResponse.json();
            console.log(apiJson);
            if (apiJson.status === "ok") {
                test_run = apiJson.response;
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
        if (event.detail.value != "NONE" && !users[event.detail.value]) return;
        let new_assignee = event.detail.value;
        new_assignee = new_assignee != "NONE" ? new_assignee : "none-none-none";
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
                if (new_assignee != "none-none-none") {
                    sendMessage("success", `Successfully changed assignee to "${users[new_assignee].username}"`);
                } else {
                    sendMessage("success", `Successfully cleared assignee from a run`);
                }
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
                sendMessage("success", `Successfully changed status from "${test_run.status}" to "${newStatus}"`)
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
    onMount(() => {
        fetchTestRunData();

        clockInterval = setInterval(() => {
            currentTime = new Date();
        }, 1000);
    });

    onDestroy(() => {
        if (clockInterval) clearInterval(clockInterval);
    });
</script>

<div class="border rounded bg-white p-2">
    {#if test_run}
        <div class="container-fluid p-0 m-0">
            <div class="row p-0 m-0">
                <div class="col-2 py-2 dropdown">
                    <button
                        class="btn {StatusButtonCSSClassMap[
                            test_run.status
                        ]} text-light"
                        type="button"
                        title={new Date(
                            test_run.end_time * 1000
                        ).toLocaleString()}
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
                                        newStatus = status.toLowerCase();
                                        handleStatus();
                                    }}>{status}</button
                                >
                            </li>
                        {/each}
                    </ul>
                </div>
                <div class="col-10 text-end py-3">
                    <p class="p-0 d-inline-block pe-4">
                        {test_run.build_job_name}
                    </p>
                    <a
                        class="d-inline-block btn btn-light"
                        href="/test_run/{id}"
                        target="_blank">#{build_number}</a
                    >
                </div>
            </div>
            {#if Object.keys(users).length > 0}
                <div class="row p-2 m-0 justify-content-end">
                    <div class="col-2 p-2 border rounded">
                        <Select
                            Item={User}
                            value={users[test_run.assignee]?.username ?? "NONE"}
                            items={userSelect}
                            on:select={handleAssign}
                        />
                    </div>
                </div>
            {/if}
            {#if InProgressStatuses.includes(test_run.status)}
                <div class="row text-sm text-muted p-0 m-0">
                    <div class="col p-2">
                        Last heartbeat: {heartbeatHuman} ago
                    </div>
                    <div class="col p-2">Started: {startedAtHuman} ago</div>
                </div>
            {/if}
        </div>
        <nav>
            <div class="nav nav-tabs" id="nav-tab-{id}" role="tablist">
                <button
                    class="nav-link active"
                    id="nav-details-tab-{id}"
                    data-bs-toggle="tab"
                    data-bs-target="#nav-details-{id}"
                    type="button"
                    role="tab"><i class="fas fa-info-circle" /> Details</button
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
                    role="tab"><i class="fas fa-rss-square" /> Events</button
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
                    role="tab"><i class="fas fa-box" /> Logs</button
                >
                <button
                    class="nav-link"
                    id="nav-discuss-tab-{id}"
                    data-bs-toggle="tab"
                    data-bs-target="#nav-discuss-{id}"
                    type="button"
                    on:click={() => (commentsOpen = true)}
                    role="tab"><i class="fas fa-comments" /> Discussion</button
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
            class="tab-content border-start border-end border-bottom"
            id="nav-tabContent-{id}"
        >
            <div
                class="tab-pane fade show active"
                id="nav-details-{id}"
                role="tabpanel"
            >
                <TestRunInfo {test_run} />
            </div>
            <div class="tab-pane fade" id="nav-resources-{id}" role="tabpanel">
                <div
                    class="accordion accordion-flush"
                    id="accordionResources-{id}"
                >
                    <ResourcesInfo
                        caption="Allocated Resources"
                        {id}
                        resources={test_run.allocated_resources}
                    />
                    <ResourcesInfo
                        caption="Terminated Resources"
                        {id}
                        resources={test_run.terminated_resources}
                    />
                    <ResourcesInfo
                        caption="Leftover Resources"
                        {id}
                        resources={test_run.leftover_resources}
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
                                    {event_container.severity.toUpperCase()} ({event_container.event_amount})
                                </button>
                            </h2>
                            <div
                                id="accordionBodyEvents{event_container.severity}-{id}"
                                class="accordion-collapse collapse"
                                data-bs-parent="#accordionEvents"
                            >
                                <div class="accordion-body">
                                    {#each event_container.last_events as event}
                                        <p class="mb-1 border font-monospace">
                                            {event}
                                        </p>
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
            <div class="tab-pane fade" id="nav-nemesis-{id}" role="tabpanel">
                <NemesisData nemesis_data={test_run.nemesis_data} />
            </div>
            <div class="tab-pane fade" id="nav-logs-{id}" role="tabpanel">
                {#if test_run.logs.length > 0}
                    <table class="table table-bordered table-sm text-center">
                        <thead>
                            <th>Log Type</th>
                            <th>Log URL</th>
                        </thead>
                        <tbody>
                            {#each test_run.logs as log}
                                <tr>
                                    <td>{log[0]}</td>
                                    <td
                                        ><a
                                            class="btn btn-primary"
                                            href={log[1]}>Link</a
                                        ></td
                                    >
                                </tr>
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
            </div>
            <div class="tab-pane fade" id="nav-discuss-{id}" role="tabpanel">
                {#if commentsOpen}
                    <TestRunComments {id} />
                {/if}
            </div>
            <div class="tab-pane fade" id="nav-issues-{id}" role="tabpanel">
                <IssueTemplate {test_run} />
                {#if issuesOpen}
                    <GithubIssues {id} />
                {/if}
            </div>
            <div class="tab-pane fade" id="nav-activity-{id}" role="tabpanel">
                {#if activityOpen}
                    <ActivityTab {id} />
                {/if}
            </div>
        </div>
    {:else}
        <div class="text-center p-2 m-1 d-flex align-items-center justify-content-center">
            <span class="spinner-border me-4" /><span class="fs-4">Loading...</span>
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
</style>
