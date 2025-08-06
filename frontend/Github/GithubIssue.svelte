<script lang="ts">
    import { run as run_1 } from 'svelte/legacy';

    import { createEventDispatcher } from "svelte";
    import Color from "color";
    import Fa from "svelte-fa";
    import { faGithub } from "@fortawesome/free-brands-svg-icons";
    import {
        faCheckCircle,
        faDotCircle,
        faExternalLinkSquareAlt,
        faTrash,
    } from "@fortawesome/free-solid-svg-icons";
    import { sendMessage } from "../Stores/AlertStore";
    import { userList } from "../Stores/UserlistSubscriber";
    import { timestampToISODate } from "../Common/DateUtils";
    import { apiMethodCall } from "../Common/ApiUtils";
    import { determineLuma } from "../Common/TextUtils";
    import { stateEncoder } from "../Common/StateManagement";

    const dispatch = createEventDispatcher();
    let users = $state({});
    run_1(() => {
        users = $userList;
    });
    let githubToken;
    const IssueColorMap = {
        open: "issue-open",
        closed: "issue-closed",
    };

    const IssueIcon = {
        open: faDotCircle,
        closed: faCheckCircle,
    };

    interface Props {
        issue?: any;
        runId: any;
        deleteEnabled?: boolean;
        aggregated?: boolean;
    }

    let {
        issue = $bindable({
        id: "",
        number: -1,
        state: "unknown",
        owner: "nobody",
        repo: "no-repo",
        title: "NO ISSUE",
        links: [],
        labels: [],
        type: "issues",
        url: "https://github.com/",
        user_id: "",
        added_on: "Mon, 1 Jan 1970 9:00:00 GMT",
    }),
        runId,
        deleteEnabled = true,
        aggregated = false
    }: Props = $props();

    let deleting = $state(false);
    let showRuns = $state(false);

    let resolvedRuns;

    const resolveRuns = async function(runs) {
        if (resolvedRuns) return resolvedRuns;
        let response = await fetch("/api/v1/get_runs_by_test_id_run_id",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(runs.map(v => [v.test_id, v.run_id]))
            }
        );

        let data = await response.json();
        if (data.status !== "ok") {
            throw new Error(data.response.arguments[0]);
        }
        resolvedRuns = data.response.runs;
        return data.response.runs;
    };

    const resolveFirstUserForAggregation = function(issue) {
        if (!issue.links) return {
            id: issue.user_id,
            date: issue.added_on,
        };
        const resolved = issue.links
            .filter(l => !!l.added_on && !!l.user_id)
            .sort((a, b) => {
                const lhs = Date.parse(a.added_on);
                const rhs = Date.parse(b.added_on);

                return lhs > rhs ? 1 : rhs > lhs ? -1 : 0;
            });

        return {
            id: resolved?.[0]?.user_id ?? issue.user_id,
            date: resolved?.[0]?.added_on ?? issue.added_on,
        };
    };

    const deleteIssue = async function () {
        deleting = true;
        try {
            if (aggregated) throw new Error("Cannot delete aggregated issues");
            let apiResponse = await fetch("/api/v1/issues/delete", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    issue_id: issue.id,
                    run_id: runId,
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                dispatch("issueDeleted", {
                    id: issue.id,
                });
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to delete an issue.\nAPI Response: ${error.response.arguments[0]}`,
                    "GithubIssue::delete"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during issue deleting",
                    "GithubIssue::delete"
                );
            }
        }
    };
</script>

<div class="row m-2">
    <div class="col rounded p-2 bg-white shadow-sm">
        <div class="d-flex">
            <div class="ms-2 align-self-center">
                <div class="mb-1 py-1 shadow-sm rounded-pill d-inline-flex {IssueColorMap[issue.state]}">
                    <div class="ms-2 me-1"><Fa icon={IssueIcon[issue.state]} /></div>
                    <div class="me-2">{issue.state}</div>
                </div>
            </div>
            <div
                class="ms-2 me-2"
                style="width: 30em;"
                title={issue.title}
            >
                <Fa icon={faGithub} /> <a target="_blank" class="link-dark" href={issue.url}>{issue.title}</a>
                <div class="text-muted ms-auto me-2">{issue.repo}#{issue.number}</div>
            </div>
            <div class="ms-2 me-2">
                {#each issue.labels as label (label.id)}
                    <button
                        class="align-items-center me-1 px-2 label-text border border-dark cursor-pointer"
                        style="color: {Color(`#${label.color}`).isDark() ? 'white' : 'black'}; background-color: #{label.color};"
                        onclick={() => {
                            dispatch("labelClick", label);
                        }}
                    >
                        <div>{label.name}</div>
                    </button>
                {/each}
            </div>
            <div class="ms-auto me-2">
                {#if Object.keys(users).length > 0}
                    <div
                        class="text-muted d-flex align-items-center"
                        title={new Date(issue.added_on).toISOString()}
                    >
                        <div>Added by <span class="fw-bold">@{users?.[resolveFirstUserForAggregation(issue).id]?.username ?? "ghost"}</span> on {timestampToISODate(new Date(resolveFirstUserForAggregation(issue).date))}</div>
                        {#if deleteEnabled && !aggregated}
                            <div class="ms-2 text-muted">
                                {#if deleting}
                                <button
                                    class="btn btn-sm btn-danger"
                                    title="Please wait"
                                    type="button"
                                >
                                    <span class="spinner-border spinner-border-sm"></span>
                                </button>
                                {:else}
                                    <button
                                        class="btn btn-sm btn-danger"
                                        title="Remove this issue from this run"
                                        type="button"
                                        data-bs-toggle="modal"
                                        data-bs-target="#modalIssueConfirmDelete-{issue.id}"
                                    >
                                        <Fa icon={faTrash} />
                                    </button>
                                {/if}
                            </div>
                        {/if}
                    </div>
                {/if}
                {#if aggregated}
                    <div class="text-end my-2">
                        {#if runId}
                            <button class="btn btn-primary" onclick={() => dispatch("submitToCurrent", issue.url)}>Add to current run</button>
                        {/if}
                        <button class="btn btn-primary" onclick={() => (showRuns = true)}>View {issue.links.length} runs</button>
                    </div>
                {/if}
            </div>
        </div>
    </div>
</div>

{#if showRuns}
    <div class="issue-run-list-modal">
        <div class="d-flex align-items-center justify-content-center p-4">
            <div class="rounded bg-white p-4 h-50">
                <div class="mb-2 d-flex border-bottom pb-2">
                    <h5>Runs for <span class="fw-bold">{issue.title}</span></h5>
                    <div class="ms-auto">
                        <button
                            class="btn btn-close"
                            onclick={() => {
                                showRuns = false;
                            }}
                        ></button>
                    </div>
                </div>
                <div>
                </div>
                    {#await resolveRuns(issue.links)}
                        <div class="mb-2 text-center p-2">
                            <span class="spinner-border spinner-border-sm"></span> Loading runs...
                        </div>
                        <div class="list-group mb-2">
                            {#each issue.links as run, idx}
                                <a class="list-group-item list-group-item-action" href="/test/{run.test_id}/runs?additionalRuns[]={run.run_id}"><Fa icon={faExternalLinkSquareAlt} /> Run#{idx+1}</a>
                            {/each}
                        </div>
                    {:then resolved}
                        <div class="list-group mb-2">
                            {#each issue.links as run, idx}
                                <a class="list-group-item list-group-item-action" href="/test/{run.test_id}/runs?additionalRuns[]={run.run_id}"><Fa icon={faExternalLinkSquareAlt} /> {resolved[run.run_id].build_id}#{resolved[run.run_id].build_number}</a>
                            {/each}
                        </div>
                    {:catch error}
                        <div class="alert alert-danger mb-2">
                            {error.message}
                        </div>
                        <div class="list-group mb-2">
                            {#each issue.links as run, idx}
                                <a class="list-group-item list-group-item-action" href="/test/{run.test_id}/runs?additionalRuns[]={run.run_id}"><Fa icon={faExternalLinkSquareAlt} /> Run#{idx+1}</a>
                            {/each}
                        </div>
                    {/await}
                <div>
                    <a class="w-100 btn btn-primary w-75 me-1" href="/workspace?state={stateEncoder([...new Set(issue.links.map(run => run.test_id))])}">Investigate selected <Fa icon={faExternalLinkSquareAlt} /></a>
                </div>
            </div>
        </div>
    </div>
{/if}

<div class="modal" tabindex="-1" id="modalIssueConfirmDelete-{issue.id}">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Deleting an issue</h5>
                <button
                    type="button"
                    class="btn-close"
                    data-bs-dismiss="modal"
                    aria-label="Close"
></button>
            </div>
            <div class="modal-body">
                <p>
                    Are you sure you want to remove <span class="fw-bold"
                        >{issue.repo}#{issue.number}</span
                    > from this run?
                </p>
            </div>
            <div class="modal-footer">
                <button
                    type="button"
                    class="btn btn-secondary"
                    data-bs-dismiss="modal">No</button
                >
                <button
                    type="button"
                    class="btn btn-danger"
                    data-bs-dismiss="modal"
                    onclick={deleteIssue}
                >
                    Yes
                </button>
            </div>
        </div>
    </div>
</div>

<style>
    .label-text {
        font-size: 0.9em;
        font-weight: 500;
        border-radius: 12px;
    }

    .label-text:hover {
        background-color: black !important;
        color: white !important;
    }

    .h-50 {
        width: 50%;
    }

    .cursor-pointer {
        cursor: pointer;
    }

    .issue-run-list-modal {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        overflow-y: scroll;
        background-color: rgba(0, 0, 0, 0.55);
        z-index: 9999;
    }
</style>
