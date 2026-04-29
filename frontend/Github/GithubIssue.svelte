<script module>
    export { GithubIssueColorMap, GithubIssueIcon } from "../Common/IssueTypes";
</script>
<script lang="ts">
    import { run as run_1 } from 'svelte/legacy';

    import { createEventDispatcher } from "svelte";
    import Color from "color";
    import Fa from "svelte-fa";
    import { faGithub } from "@fortawesome/free-brands-svg-icons";
    import {
        faExternalLinkSquareAlt,
        faTrash,
    } from "@fortawesome/free-solid-svg-icons";
    import { sendMessage } from "../Stores/AlertStore";
    import { userList } from "../Stores/UserlistSubscriber";
    import { timestampToISODate } from "../Common/DateUtils";
    import { stateEncoder } from "../Common/StateManagement";
    import type { GithubSubtype, Link, TestRun } from '../Common/IssueTypes';
    import { GithubIssueColorMap, GithubIssueIcon, resolveRuns as resolveRunsHelper, resolveFirstUserForAggregation as resolveFirstUserHelper, deleteIssue as deleteIssueHelper } from '../Common/IssueTypes';
    import { getUser } from '../Common/UserUtils';

    const dispatch = createEventDispatcher();
    let users = $state({});
    run_1(() => {
        users = $userList;
    });


    interface Props {
        issue?: GithubSubtype;
        runId: string;
        deleteEnabled?: boolean;
        aggregated?: boolean;
    }

    let {
        issue = $bindable({
        id: "",
        subtype: "github",
        number: "-1",
        state: "open",
        owner: "nobody",
        repo: "no-repo",
        title: "NO ISSUE",
        links: [],
        labels: [],
        type: "issues",
        assignees: [],
        url: "https://github.com/",
        user_id: "",
        event_id: "",
        added_on: "Mon, 1 Jan 1970 9:00:00 GMT",
    }),
        runId,
        deleteEnabled = true,
        aggregated = false
    }: Props = $props();

    let deleting = $state(false);
    let showRuns = $state(false);

    let resolvedRuns: {
        [key: string]: TestRun,
    };

    const resolveRuns = async function(links: Link[]) {
        resolvedRuns = await resolveRunsHelper(links, resolvedRuns);
        return resolvedRuns;
    };

    const resolveFirstUserForAggregation = function(issue: GithubSubtype) {
        return resolveFirstUserHelper(issue);
    };

    const deleteIssue = async function () {
        deleting = true;
        try {
            await deleteIssueHelper({
                issueId: issue.id,
                runId,
                aggregated,
                onDeleted: (id) => dispatch("issueDeleted", { id }),
                onError: (msg) => sendMessage("error", msg, "GithubIssue::delete"),
            });
        } finally {
            deleting = false;
        }
    };
</script>

<div class="row m-2">
    <div class="col rounded p-2 bg-white shadow-sm">
        <div class="d-flex">
            <div class="ms-2 align-self-center flex-shrink-0" style="width: 10em;">
                <div class="mb-1 py-1 shadow-sm rounded-pill d-inline-flex {GithubIssueColorMap[issue.state]}">
                    <div class="ms-2 me-1"><Fa icon={GithubIssueIcon[issue.state]} /></div>
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
            <div class="ms-auto me-2 d-flex align-items-center gap-2">
                {#if Object.keys(users).length > 0}
                    <div
                        class="text-muted d-flex align-items-center"
                        title={new Date(issue.added_on).toISOString()}
                    >
                        <div>Added by <span class="fw-bold">@{ getUser(resolveFirstUserForAggregation(issue).id, users).username }</span> on {timestampToISODate(new Date(resolveFirstUserForAggregation(issue).date))}</div>
                        {#if deleteEnabled && !aggregated}
                            <div class="ms-2 text-muted">
                                {#if deleting}
                                <button
                                    class="btn btn-sm btn-danger"
                                    title="Please wait"
                                    type="button"
                                    aria-label="progress spinner"
                                >
                                    <span class="spinner-border spinner-border-sm"></span>
                                </button>
                                {:else}
                                    <button
                                        class="btn btn-sm btn-danger"
                                        title="Remove this issue from this run"
                                        aria-label="Remove this issue from this run"
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
                    <div class="d-flex gap-1">
                        {#if runId}
                            <button class="btn btn-sm btn-primary" onclick={() => dispatch("submitToCurrent", issue.url)}>Add to current run</button>
                        {/if}
                        <button class="btn btn-sm btn-primary" onclick={() => (showRuns = true)}>View {issue.links.length} runs</button>
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
                        >X</button>
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
