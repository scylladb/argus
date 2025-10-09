<script lang="ts">
    import {faCheckCircle, faCopy, faDotCircle, faLink, faPlus} from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import { sendMessage } from "../Stores/AlertStore";
    import ModalWindow from "../Common/ModalWindow.svelte";
    import { createEventDispatcher } from "svelte";



    interface Props {
        event: any;
        similars?: any;
        duplicates?: number;
        // eslint-disable-next-line @typescript-eslint/no-empty-function
        toggleDuplicates?: any;
        duplicatesVisible?: boolean;
        duplicateParent?: { severity: string; index: number } | null;
        display?: boolean;
        filterString?: string;
    }

    let {
        event,
        similars = [],
        duplicates = 0,
        toggleDuplicates = () => {},
        duplicatesVisible = false,
        duplicateParent = null,
        display = true,
        filterString = ""
    }: Props = $props();

    const dispatch = createEventDispatcher();

    let showSimilars = $state(false);
    let fetchingIssues = $state(false);
    let similarRunsInfo = $state({});

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

<div
    data-event-key={`event-${event.severity}-${event.index}`}
    class:d-none={!display || shouldFilter(filterString)}
    class="mb-2 p-2 shadow rounded font-monospace"
    class:bg-info-light={duplicates === -1}
    class:bg-white={duplicates !== -1}
>
<style>
    /* Light blue for duplicate events */
    .bg-info-light {
        background-color: #e3f2fd !important;
    }
</style>
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
                <button class="btn btn-warning btn-sm d-flex align-items-center gap-2" onclick={toggleSimilars}>
                    <Fa icon={faLink} /><span>View {similars.length} Similar Events</span>
                </button>
            {/if}
            {#if duplicates > 0}
                <button
                    class="btn btn-sm d-flex align-items-center gap-2"
                    class:btn-primary={duplicatesVisible}
                    class:btn-info={!duplicatesVisible}
                    onclick={() => { toggleDuplicates(event); }}>
                    <Fa icon={faCopy} />
                    <span>{duplicatesVisible ? "Hide Duplicates" : `Show ${duplicates} Duplicates`}</span>
                </button>
            {:else if duplicates === -1 && duplicateParent}
                <button
                    class="btn btn-sm btn-outline-primary d-flex align-items-center gap-2"
                    onclick={() => { toggleDuplicates(duplicateParent, event.index); }}>
                    <Fa icon={faCopy} />
                    <span>Hide Duplicates</span>
                </button>
            {/if}
            <button
                class="btn btn-light"
                title="Copy event text"
                onclick={() => {
                    navigator.clipboard.writeText(event.eventText);
                    sendMessage("success", "Event text has been copied to your clipboard");
                }}
            >
                <Fa icon={faCopy} />
            </button>
        </div>
        <div class="w-100"></div>
        <div class="ms-2 mb-2 rounded px-2 bg-light-two" title="Timestamp">{event.eventTimestamp}</div>
        {#if event.receiveTimestamp}
            <div class="ms-2 mb-2 rounded px-2 bg-light-two" title="Timestamp">Received: {event.receiveTimestamp}</div>
        {/if}
        <div class="w-100"></div>
        {#if event.fields.node}
            <div class="ms-2 mb-2 rounded px-2 bg-light-two fs-6 justify-self-start">{event.fields.node}</div>
        {/if}
        {#if event.fields.target_node}
            <div class="ms-2 mb-2 rounded px-2 bg-light-two fs-6 justify-self-start">{event.fields.target_node}</div>
        {/if}
        <div class="w-100"></div>
        {#if event.fields.known_issue}
            <div class="ms-2 mb-2 rounded px-2 bg-info fs-6 justify-self-start">
                Known issue: <a href={event.fields.known_issue} class="link-dark">{event.fields.known_issue}</a>
            </div>
        {/if}
        <div class="w-100"></div>
        {#if event.fields.nemesis_name}
            <div class="ms-2 mb-2 rounded px-2 bg-dark text-light fs-6 justify-self-start">
                Nemesis: {event.fields.nemesis_name}
            </div>
        {/if}
        <div class="w-100"></div>
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
        {#snippet title()}

                Similar Events ({Object.keys(similarRunsInfo).length})

            {/snippet}
        {#snippet body()}

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
                                                    <div class="mb-1 d-flex align-items-center">
                                                        <div class="btn-group" style="width: 128px">
                                                            <button
                                                                class:btn-open={issue.state === "open"}
                                                                class:btn-closed={issue.state !== "open"}
                                                                class="btn btn-sm"
                                                                title="Add this issue to the current run"
                                                                onclick={() => dispatch("issueAttach", { url: issue.url })}
                                                            >
                                                                <Fa icon={faPlus}/>
                                                            </button>
                                                            <a href={issue.url} class:btn-open={issue.state === "open"} class:btn-closed={issue.state !== "open"} target="_blank" class="btn btn-sm">
                                                                <Fa icon={issue.state === "open" ? faDotCircle : faCheckCircle}/> #{issue.number}
                                                            </a>
                                                        </div>
                                                        <div class="ms-2 overflow-ellipsis text-truncate" style="max-width: 512px" title="{issue.title}">
                                                            {issue.title}
                                                        </div>
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

            {/snippet}
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

    .btn-open {
        --bs-btn-color: #fff;
        --bs-btn-bg: #347d39;
        --bs-btn-border-color: #2f5c32;
        --bs-btn-hover-color: #fff;
        --bs-btn-hover-bg: #29722e;
        --bs-btn-hover-border-color: rgb(32, 68, 35);
        --bs-btn-focus-shadow-rgb: 225, 83, 97;
        --bs-btn-active-color: #fff;
        --bs-btn-active-bg: #349b3b;
        --bs-btn-active-border-color: #3a693d;
        --bs-btn-active-shadow: inset 0 3px 5px rgba(0, 0, 0, 0.125);
        --bs-btn-disabled-color: #fff;
        --bs-btn-disabled-bg: #6fc575;
        --bs-btn-disabled-border-color: #597e5c;
    }

    .btn-closed {
        --bs-btn-color: #fff;
        --bs-btn-bg: #8256d0;
        --bs-btn-border-color: #7459a3;
        --bs-btn-hover-color: #fff;
        --bs-btn-hover-bg: #6843a8;
        --bs-btn-hover-border-color: #624496;
        --bs-btn-focus-shadow-rgb: 225, 83, 97;
        --bs-btn-active-color: #fff;
        --bs-btn-active-bg: #9255fa;
        --bs-btn-active-border-color: #ba95fa;
        --bs-btn-active-shadow: inset 0 3px 5px rgba(0, 0, 0, 0.125);
        --bs-btn-disabled-color: #fff;
        --bs-btn-disabled-bg: #b19cd4;
        --bs-btn-disabled-border-color: #8e82a1;
    }
</style>
