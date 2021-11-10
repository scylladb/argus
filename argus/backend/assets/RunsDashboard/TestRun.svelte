<script>
    import { onMount, onDestroy } from "svelte";
    import humanizeDuration from "humanize-duration";
    import ResourcesInfo from "./ResourcesInfo.svelte";
    import NemesisData from "./NemesisData.svelte";
    import TestRunComments from "./TestRunComments.svelte";
    import IssueTemplate from "./IssueTemplate.svelte";
    export let id = "";
    export let build_number = -1;
    let test_run = undefined;
    let interval = 20 * 1000;
    let intervalId;
    let heartbeatHuman = "";
    let currentTime = new Date();
    let clockInterval;
    $: heartbeatHuman = humanizeDuration(
        currentTime - test_run?.heartbeat * 1000,
        { round: true }
    );

    const titleCase = function (string) {
        return string[0].toUpperCase() + string.slice(1).toLowerCase();
    };
    let cmd_hydraInvestigateShowMonitor = `hydra investigate show-monitor ${id}`;
    let cmd_hydraInvestigateShowLogs = `hydra investigate show-logs ${id}`;

    const fetchTestRunData = function () {
        fetch("/api/v1/test_run", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                test_id: id,
            }),
        })
            .then((res) => {
                if (res.status == 200) {
                    return res.json();
                } else {
                    console.log("Error fetching test_run");
                    console.log(res);
                }
            })
            .then((res) => {
                if (res.status === "ok") {
                    test_run = res.response;
                    if (build_number == -1) {
                        build_number = parseInt(
                            test_run.build_job_url.split("/").reverse()[1]
                        );
                    }
                    console.log(test_run);
                } else {
                    console.log("Something went wrong...");
                    console.log(res);
                }
            });
    };

    onMount(() => {
        fetchTestRunData();

        intervalId = setInterval(() => {
            fetchTestRunData();
        }, interval);

        clockInterval = setInterval(() => {
            currentTime = new Date();
        }, 1000);
    });

    onDestroy(() => {
        if (intervalId) clearInterval(intervalId);
        if (clockInterval) clearInterval(clockInterval);
    });
</script>

<div class="border rounded">
    {#if test_run}
        <div class="container-fluid p-0 m-0">
            <div class="row p-0 m-0">
                <div class="col-1 py-3">
                    {#if test_run.status == "running"}
                        <div
                            class="p-2 m-0 border rounded test-status-bg-running d-flex justify-content-center cursor-question"
                        >
                            <span
                                class="spinner-border spinner-border-sm d-inline-block"
                            />
                        </div>
                        
                    {:else if test_run.status == "passed" || test_run.status == "failed"}
                        <p
                            class="p-2 m-0 border rounded test-status-bg-{test_run.status} d-inline-block cursor-question"
                            title={new Date(
                                test_run.end_time * 1000
                            ).toLocaleString()}
                        >
                            {test_run.status.toUpperCase()}
                        </p>
                    {/if}
                </div>
                <div class="col-11 text-end py-3">
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
            {#if ["running", "created"].includes(test_run.status)}
                <div class="row text-sm text-muted p-0 m-0">
                    <div class="col p-2">Last heartbeat: {heartbeatHuman} ago</div>
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
                    role="tab"><i class="fas fa-comments" /> Discussion</button
                >
                <button
                    class="nav-link"
                    id="nav-issues-tab-{id}"
                    data-bs-toggle="tab"
                    data-bs-target="#nav-issues-{id}"
                    type="button"
                    role="tab"><i class="fas fa-code-branch" /> Issues</button
                >
            </div>
        </nav>
        <div class="tab-content" id="nav-tabContent-{id}">
            <div
                class="tab-pane fade show active"
                id="nav-details-{id}"
                role="tabpanel"
            >
                <div class="container-fluid">
                    <div class="row">
                        <div class="col-6 p-2">
                            Details
                            <ul>
                                <li>
                                    <span class="fw-bold">Test:</span>
                                    {test_run.group}.{test_run.name}
                                </li>
                                <li>
                                    <span class="fw-bold">Id:</span>
                                    {test_run.id}
                                </li>
                                <li>
                                    Start Time: {new Date(
                                        test_run.start_time * 1000
                                    ).toLocaleString()}
                                </li>
                                {#if test_run.end_time != -1}
                                <li>
                                    End Time: {new Date(
                                        test_run.end_time * 1000
                                    ).toLocaleString()}
                                </li>
                                {/if}
                                <li>
                                    Started by: {test_run.started_by ??
                                        "Unknown, probably jenkins"}
                                </li>
                                <li>
                                    Build Job: <a href={test_run.build_job_url}
                                        >{test_run.build_job_name}</a
                                    >
                                </li>
                            </ul>

                            <div class="btn-group">
                                <a
                                    href="https://jenkins.scylladb.com/view/QA/job/QA-tools/job/hydra-show-monitor/parambuild/?test_id={test_run.id}"
                                    class="btn btn-primary"
                                    target="_blank"
                                    aria-current="page"
                                    ><i class="fas fa-search" />Restore
                                    Monitoring Stack</a
                                >
                                <button
                                    type="button"
                                    class="btn btn-primary"
                                    on:click={() => {
                                        navigator.clipboard.writeText(
                                            cmd_hydraInvestigateShowMonitor
                                        );
                                    }}
                                    ><i class="far fa-copy" /> Hydra Monitor</button
                                >
                                <button
                                    type="button"
                                    class="btn btn-primary"
                                    on:click={() => {
                                        navigator.clipboard.writeText(
                                            cmd_hydraInvestigateShowLogs
                                        );
                                    }}
                                    ><i class="far fa-copy" /> Hydra Logs</button
                                >
                            </div>
                        </div>
                        <div class="col-6 p-2">
                            System Information:
                            <ul>
                                <li>
                                    <span class="fw-bold">Backend:</span>
                                    {test_run.cloud_setup.backend}
                                </li>
                                <li>
                                    <span class="fw-bold">Region:</span>
                                    {test_run.region_name.join(", ")}
                                </li>
                                <li>
                                    AMI ImageId: {test_run.cloud_setup.db_node
                                        .image_id}
                                </li>
                                <li>
                                    Scylla Version: {test_run.packages[0]
                                        ?.version ?? "Unknown yet"}/{test_run
                                        .packages[0]?.revision_id ??
                                        "Unknown yet"}
                                </li>
                                <li>
                                    Instance Type: {test_run.cloud_setup.db_node
                                        .instance_type}
                                </li>
                                <li>
                                    Node Amount: {test_run.cloud_setup.db_node
                                        .node_amount}
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
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
                <TestRunComments {id} />
            </div>
            <div class="tab-pane fade" id="nav-issues-{id}" role="tabpanel">
                <IssueTemplate {test_run} />
            </div>
        </div>
    {:else}
        <div class="text-center p-2 m-1">
            <span class="spinner-border" /><span class="fs-4">Loading...</span>
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

    .test-status-fg-running {
        color: rgb(221, 221, 50);
    }

    .test-status-bg-passed {
        color: white;
        background-color: rgb(37, 143, 37);
        border-color: rgb(37, 143, 37);
    }

    .test-status-bg-running {
        color: white;
        background-color: rgb(221, 221, 50);
        border-color: rgb(221, 221, 50);
    }

    .test-status-bg-failed {
        color: white;
        background-color: rgb(185, 23, 23);
        border-color: rgb(185, 23, 23);
    }

    .cursor-question {
        cursor: help;
    }
</style>
