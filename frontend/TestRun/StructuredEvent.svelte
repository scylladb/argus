<script>
    import {faCopy, faDotCircle, faLink} from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import { sendMessage } from "../Stores/AlertStore";
    import ModalWindow from "../Common/ModalWindow.svelte";

    export let event;
    export let similars = [];
    export let display = true;
    export let filterString = "";

    let showSimilars = false;
    let fetchingIssues = false;
    let similarRunsInfo = {};

    const shouldFilter = function (filterString) {
        if (!filterString) return;
        try {
            return !(new RegExp(filterString.toLowerCase()).test((event.eventText.toLowerCase() ?? "")));
        } catch {
            return false;
        }
    };

    const toggleSimilars = async () => {
        showSimilars = !showSimilars;

        // Fetch build IDs and issues for all similar runs when opening the modal
        if (showSimilars && similars.length > 0 && Object.keys(similarRunsInfo).length === 0) {
            fetchingIssues = true;
            try {
                const response = await fetch("/api/v1/client/sct/similar_runs_info", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        run_ids: similars,
                    }),
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.status === "ok") {
                        similarRunsInfo = data.response;
                    } else {
                        console.error("Error fetching similar runs info:", data);
                    }
                } else {
                    console.error("Failed to fetch similar runs info:", response.statusText);
                }
            } catch (error) {
                console.error("Error fetching similar runs info:", error);
                sendMessage("error", "Error fetching similar runs info", "StructuredEvent::toggleSimilars");
            } finally {
                fetchingIssues = false;
            }
        }
    };

    function closeSimilarModal() {
        showSimilars = false;
    }
</script>

<div class:d-none={!display || shouldFilter(filterString)} class="mb-2 p-2 shadow rounded bg-white font-monospace">
    <div class="event-header d-flex align-items-start flex-wrap">
        <div class="ms-2 mb-2 bg-dark text-light rounded px-2">{event.eventType}</div>
        <div class="ms-2 mb-2 rounded px-2 severity-{event.severity.toLowerCase()}">{event.severity}</div>
        <div
            class="ms-2 mb-2 rounded px-2 bg-light-two d-flex align-items-center"
            title="Event period type: {event.fields.period_type}"
        >
            <Fa icon={faDotCircle} />
            <span class="ms-2"
                >{event.fields.period_type}
                {#if event.fields.duration}
                    (duration: {event.fields.duration})
                {/if}</span
            >
        </div>
        {#each event.nemesis ?? [] as nemesis}
            <div class="ms-2 mb-2 rounded px-2 status-{nemesis.status.toLowerCase()}">{nemesis.name}</div>
        {/each}
        <div class="ms-auto mb-2 rounded px-2 d-flex gap-2">
            {#if (event.severity === "ERROR" || event.severity === "CRITICAL") && similars.length > 0}
                <button class="btn btn-warning btn-sm d-flex align-items-center gap-2" on:click={toggleSimilars}>
                    <Fa icon={faLink} /><span>View {similars.length} Similar Events</span>
                </button>
            {/if}
            <button
                class="btn btn-light"
                title="Copy event text"
                on:click={() => {
                    navigator.clipboard.writeText(event.eventText);
                    sendMessage("success", "Event text has been copied to your clipboard");
                }}
            >
                <Fa icon={faCopy} />
            </button>
        </div>
        <div class="w-100" />
        <div class="ms-2 mb-2 rounded px-2 bg-light-two" title="Timestamp">{event.eventTimestamp}</div>
        {#if event.receiveTimestamp}
            <div class="ms-2 mb-2 rounded px-2 bg-light-two" title="Timestamp">Received: {event.receiveTimestamp}</div>
        {/if}
        <div class="w-100" />
        {#if event.fields.node}
            <div class="ms-2 mb-2 rounded px-2 bg-light-two fs-6 justify-self-start">{event.fields.node}</div>
        {/if}
        {#if event.fields.target_node}
            <div class="ms-2 mb-2 rounded px-2 bg-light-two fs-6 justify-self-start">{event.fields.target_node}</div>
        {/if}
        <div class="w-100" />
        {#if event.fields.known_issue}
            <div class="ms-2 mb-2 rounded px-2 bg-info fs-6 justify-self-start">
                Known issue: <a href={event.fields.known_issue} class="link-dark">{event.fields.known_issue}</a>
            </div>
        {/if}
        <div class="w-100" />
        {#if event.fields.nemesis_name}
            <div class="ms-2 mb-2 rounded px-2 bg-dark text-light fs-6 justify-self-start">
                Nemesis: {event.fields.nemesis_name}
            </div>
        {/if}
        <div class="w-100" />
        {#if event.fields.duration}
            <div class="ms-2 mb-2 rounded px-2 bg-light-two">
                <div>Duration: {event.fields.duration}</div>
            </div>
        {/if}
    </div>
    <pre class="bg-light-one rounded m-2 p-2 log-line">{event.eventText}</pre>
</div>

{#if showSimilars}
    <ModalWindow widthClass="w-75" on:modalClose={closeSimilarModal}>
        <svelte:fragment slot="title">
            Similar Events ({Object.keys(similarRunsInfo).length})
        </svelte:fragment>
        <svelte:fragment slot="body">
            {#if fetchingIssues}
                <div class="d-flex justify-content-center align-items-center" style="min-height: 200px;">
                    <div class="spinner-border" role="status">
                        <span class="visually-hidden">Loading similar runs information...</span>
                    </div>
                    <span class="ms-3">Loading similar runs information...</span>
                </div>
            {:else}
                <div class="table-responsive">
                    <table class="table table-striped table-hover">
                        <thead>
                            <tr>
                                <th>Build ID</th>
                                <th>Start Time</th>
                                <th>Version</th>
                                <th>Issues</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each similars.filter(runId => similarRunsInfo[runId]) as runId}
                                <tr>
                                    <td>
                                        <a href="/tests/scylla-cluster-tests/{runId}" target="_blank" title={runId}>
                                            {similarRunsInfo[runId]?.build_id || runId}
                                        </a>
                                    </td>
                                    <td class="date-column">
                                        {#if similarRunsInfo[runId]?.start_time}
                                            {new Date(similarRunsInfo[runId].start_time).toLocaleDateString("en-CA")}
                                        {:else}
                                            -
                                        {/if}
                                    </td>
                                    <td>
                                        {#if similarRunsInfo[runId]?.version}
                                            {similarRunsInfo[runId].version}
                                        {:else}
                                            -
                                        {/if}
                                    </td>
                                    <td>
                                        {#if similarRunsInfo[runId]?.issues?.length}
                                            {#each similarRunsInfo[runId].issues as issue}
                                                <div class="issue-item mb-1">
                                                    <a href={issue.url} target="_blank" class="issue-link">
                                                        <span
                                                            class="badge {issue.state === 'open'
                                                                ? 'issue-open'
                                                                : 'issue-closed'}">#{issue.number}</span
                                                        >
                                                        {issue.title}
                                                    </a>
                                                </div>
                                            {/each}
                                        {:else}
                                            <span class="text-muted">No issues</span>
                                        {/if}
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            {/if}
        </svelte:fragment>
    </ModalWindow>
{/if}

<style>
    .log-line {
        white-space: pre-wrap;
    }

    .severity-warning {
        background-color: #ffd416;
        color: black;
    }
    .severity-normal {
        background-color: #2d98c2;
        color: white;
    }
    .severity-debug {
        background-color: #7e6262;
        color: white;
    }
    .severity-info {
        background-color: #777777;
        color: white;
    }
    .severity-error {
        background-color: #ff0000;
        color: white;
    }
    .severity-critical {
        background-color: #692121;
        color: white;
    }
    .status-succeeded {
        background-color: #198754;
        color: white;
    }
    .status-failed {
        background-color: #dc3545;
        color: white;
    }
    .status-skipped {
        background-color: #1c1f23;
        color: white;
    }

    .issues-container {
        max-height: 150px;
        overflow-y: auto;
    }

    .issue-link {
        text-decoration: none;
        color: #212529;
    }

    .issue-link:hover {
        text-decoration: underline;
    }

    .date-column {
        width: 100px;
    }
</style>
