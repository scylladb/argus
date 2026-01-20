<script lang="ts" module>
    import type { SCTEvent } from "./SctEvents.svelte";

    export interface SimilarEventExtended extends SCTEvent {
        build_id?: string;
        start_time?: string;
        version?: string;
        issues?: Array<{
            url: string;
            number: number;
            title: string;
            state: string;
        }>;
    }
</script>

<script lang="ts">
    import { faCheckCircle, faDotCircle, faExclamationTriangle, faPlus } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import { sendMessage } from "../../Stores/AlertStore";
    import ModalWindow from "../../Common/ModalWindow.svelte";
    import { timestampToISODate } from "../../Common/DateUtils";

    interface Props {
        event: SCTEvent;
        runId: string;
        issueAttach?: (url: string) => void;
    }

    let { event, runId, issueAttach }: Props = $props();
    let showModal = $state(false);
    let similarEvents: SimilarEventExtended[] = $state([]);
    let loadingSimilars = $state(false);
    let fetchingRunInfo = $state(false);

    const fetchSimilarEvents = async function () {
        loadingSimilars = true;
        try {
            const response = await fetch(`/api/v1/client/sct/${runId}/event/similar`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    severity: event.severity,
                    ts: event.ts,
                    limit: 50
                })
            });

            if (!response.ok) {
                throw new Error(`Failed to fetch similar events: ${response.statusText}`);
            }

            const data = await response.json();
            if (data.status === "ok") {
                similarEvents = data.response || [];
                // Fetch run info for all similar events
                if (similarEvents.length > 0) {
                    await fetchRunsInfo();
                }
            } else {
                throw new Error(data.response || "Unknown error");
            }
        } catch (error) {
            console.error("Error fetching similar events:", error);
            const errorMessage = error instanceof Error ? error.message : String(error);
            sendMessage("error", `Failed to fetch similar events: ${errorMessage}`, "SctEventSimilars::fetchSimilarEvents");
        } finally {
            loadingSimilars = false;
        }
    };

    const fetchRunsInfo = async function () {
        fetchingRunInfo = true;
        try {
            const runIds = similarEvents.map(e => e.run_id);
            const response = await fetch("/api/v1/client/sct/similar_runs_info", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    run_ids: runIds,
                }),
            });

            if (response.ok) {
                const data = await response.json();
                if (data.status === "ok") {
                    const runsInfo = data.response;
                    // Merge run info into similar events
                    similarEvents = similarEvents.map(event => ({
                        ...event,
                        build_id: runsInfo[event.run_id]?.build_id,
                        start_time: runsInfo[event.run_id]?.start_time,
                        version: runsInfo[event.run_id]?.version,
                        issues: runsInfo[event.run_id]?.issues || [],
                    }));
                } else {
                    console.error("Error fetching similar runs info:", data);
                }
            } else {
                console.error("Failed to fetch similar runs info:", response.statusText);
            }
        } catch (error) {
            console.error("Error fetching similar runs info:", error);
            sendMessage("error", "Error fetching similar runs info", "SctEventSimilars::fetchRunsInfo");
        } finally {
            fetchingRunInfo = false;
        }
    };

    const toggleModal = async function () {
        if (!showModal && similarEvents.length === 0) {
            await fetchSimilarEvents();
        }
        showModal = !showModal;
    };

    const closeModal = function () {
        showModal = false;
    };

    const canShowSimilars = $derived(event.severity === "ERROR" || event.severity === "CRITICAL");
</script>

{#if canShowSimilars}
    <button
        class="btn btn-sm btn-warning d-flex align-items-center gap-2"
        onclick={toggleModal}
        disabled={loadingSimilars}
    >
        <Fa icon={faExclamationTriangle}/>
        {#if loadingSimilars}
            <span class="spinner-border spinner-border-sm"></span>
        {:else if similarEvents.length > 0}
            View {similarEvents.length} Similar Events
        {:else}
            Find Similar Events
        {/if}
    </button>
{/if}

{#if showModal}
    <ModalWindow widthClass="w-75" on:modalClose={closeModal}>
        {#snippet title()}
            Similar Events {#if similarEvents.length > 0}({similarEvents.length}){/if}
        {/snippet}
        {#snippet body()}
            {#if loadingSimilars || fetchingRunInfo}
                <div class="d-flex justify-content-center align-items-center" style="min-height: 200px;">
                    <div class="spinner-border" role="status">
                        <span class="visually-hidden">Loading similar events...</span>
                    </div>
                    <span class="ms-3">
                        {#if loadingSimilars}
                            Loading similar events...
                        {:else}
                            Loading run information...
                        {/if}
                    </span>
                </div>
            {:else if similarEvents.length === 0}
                <div class="text-center text-muted p-4">
                    <p class="fs-5">No similar events found</p>
                    <p class="small">This event doesn't have any similar patterns in other test runs.</p>
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
                            {#each similarEvents as similarEvent}
                                <tr>
                                    <td>
                                        <a
                                            href="/tests/scylla-cluster-tests/{similarEvent.run_id}"
                                            target="_blank"
                                            title={similarEvent.run_id}
                                        >
                                            {#if similarEvent.build_id}
                                                {similarEvent.build_id}
                                            {:else}
                                                {similarEvent.run_id.slice(0, 8)}...
                                            {/if}
                                        </a>
                                    </td>
                                    <td class="date-column">
                                        {#if similarEvent.start_time}
                                            {timestampToISODate(similarEvent.start_time)}
                                        {:else}
                                            -
                                        {/if}
                                    </td>
                                    <td>
                                        {#if similarEvent.version}
                                            <span class="badge bg-secondary">{similarEvent.version}</span>
                                        {:else}
                                            -
                                        {/if}
                                    </td>
                                    <td>
                                        {#if similarEvent.issues && similarEvent.issues.length > 0}
                                            {#each similarEvent.issues as issue}
                                                <div class="mb-1 d-flex align-items-center">
                                                    <div class="btn-group" style="width: 128px">
                                                        <button
                                                            class:btn-open={issue.state === "open"}
                                                            class:btn-closed={issue.state !== "open"}
                                                            class="btn btn-sm"
                                                            title="Add this issue to the current run"
                                                            onclick={() => issueAttach?.(issue.url)}
                                                        >
                                                            <Fa icon={faPlus}/>
                                                        </button>
                                                        <a
                                                            href={issue.url}
                                                            class:btn-open={issue.state === "open"}
                                                            class:btn-closed={issue.state !== "open"}
                                                            target="_blank"
                                                            class="btn btn-sm"
                                                        >
                                                            <Fa icon={issue.state === "open" ? faDotCircle : faCheckCircle}/> #{issue.number}
                                                        </a>
                                                    </div>
                                                    <div class="ms-2 overflow-ellipsis text-truncate" style="max-width: 400px" title="{issue.title}">
                                                        {issue.title}
                                                    </div>
                                                </div>
                                            {/each}
                                        {:else}
                                            <span class="text-muted small">No issues</span>
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
    .btn-open {
        background-color: #28a745;
        color: white;
        border-color: #28a745;
    }

    .btn-open:hover {
        background-color: #218838;
        border-color: #1e7e34;
    }

    .btn-closed {
        background-color: #6c757d;
        color: white;
        border-color: #6c757d;
    }

    .btn-closed:hover {
        background-color: #5a6268;
        border-color: #545b62;
    }

    .date-column {
        white-space: nowrap;
    }

    .overflow-ellipsis {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
</style>
