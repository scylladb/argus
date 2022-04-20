<script>
    import { createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import { faGithub } from "@fortawesome/free-brands-svg-icons";
    import {
        faCheckCircle,
        faDotCircle,
        faTrash,
    } from "@fortawesome/free-solid-svg-icons";
    import { sendMessage } from "../Stores/AlertStore";
    import { userList } from "../Stores/UserlistSubscriber";
    import { timestampToISODate } from "../Common/DateUtils";
    import { apiMethodCall } from "../Common/ApiUtils";
    import { determineLuma } from "../Common/TextUtils";

    const dispatch = createEventDispatcher();
    let users = {};
    $: users = $userList;
    let githubToken;
    const IssueColorMap = {
        open: "issue-open",
        closed: "issue-closed",
    };

    const IssueIcon = {
        open: faDotCircle,
        closed: faCheckCircle,
    };
    export let issue = {
        group_id: "",
        id: "",
        issue_number: -1,
        last_status: "unknown",
        owner: "nobody",
        release_id: "",
        repo: "no-repo",
        run_id: "",
        test_id: "",
        title: "NO ISSUE",
        runs: [],
        type: "issues",
        url: "https://github.com/",
        user_id: "",
        added_on: "Mon, 1 Jan 1970 9:00:00 GMT",
    };

    export let deleteEnabled = true;
    export let aggregated = false;

    let deleting = false;

    const fetchGithubToken = async function() {
        let tokenRequest = await apiMethodCall("/api/v1/profile/github/token", undefined, "GET");
        if (tokenRequest.status != "ok") {
            return Promise.reject(new Error('noToken'));
        } else {
            return Promise.resolve(tokenRequest.response);
        }
    };

    const fetchIssueState = async function() {
        if (!githubToken) {
            try {
                githubToken = await fetchGithubToken();
            } catch (error) {
                sendMessage("error", "Github Oauth token not found.");
                return;
            }
        }
        let issue_url = `https://api.github.com/repos/${issue.owner}/${issue.repo}/issues/${issue.issue_number}`;
        let issueStateResponse = await fetch(issue_url, {
            headers: {
                "Accept": "application/vnd.github.v3+json",
                "Authorization": `token ${githubToken}`,
            }
        });
        if (issueStateResponse.status < 200 || issueStateResponse.status >= 300) {
            return Promise.reject(new Error('API Error'));
        }

        if (parseInt(issueStateResponse.headers.get("x-ratelimit-remaining")) === 0) {
            return Promise.reject(new Error('Rate limit exceeded'));
        }
        return issueStateResponse.json();
    };


    const deleteIssue = async function () {
        deleting = true;
        try {
            let apiResponse = await fetch("/api/v1/issues/delete", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    id: issue.id,
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
                    `Unable to delete an issue.\nAPI Response: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during issue deletiong"
                );
            }
        }
    };
</script>

<div class="row m-2">
    <div class="col rounded p-2 bg-white shadow-sm">
        <div class="d-flex">
            {#await fetchIssueState()}
                <div
                    class="me-2"
                    style="width: 30em;"
                    title={issue.title}
                >
                    <Fa icon={faGithub} /> <a target="_blank" class="link-dark" href={issue.url}>{issue.title}</a>
                </div>
                <div class="ms-2 me-2">
                    <span class="spinner-border spinner-border-sm"></span> Loading issue state...
                </div>
            {:then issueState}
                <div class="ms-2 align-self-center">
                    <div class="mb-1 py-1 shadow-sm rounded-pill d-inline-flex {IssueColorMap[issueState.state]}">
                        <div class="ms-2 me-1"><Fa icon={IssueIcon[issueState.state]} /></div>
                        <div class="me-2">{issueState.state}</div>
                    </div>
                </div>
                <div
                    class="ms-2 me-2"
                    style="width: 30em;"
                    title={issue.title}
                >
                    <Fa icon={faGithub} /> <a target="_blank" class="link-dark" href={issue.url}>{issue.title}</a>
                    <div class="text-muted ms-auto me-2">{issue.repo}#{issue.issue_number}</div>
                </div>
                <div class="ms-2 me-2">
                    {#each issueState.labels as label (label.id)}
                        <div
                            class="d-inline-block align-items-center me-1 px-2 rounded-pill label-text"
                            style="color: {determineLuma(label.color) ? '#ffffff' : 'black'}; background-color: #{label.color};"
                        >
                            <div>{label.name}</div>
                        </div>
                    {/each}
                </div>
            {:catch error}
                <div class="ms-2 me-2">
                    Error fetching state: {error?.message ?? "Unknown"}
                </div>
            {/await}
            <div class="ms-auto me-2">
                {#if Object.keys(users).length > 0}
                    <div
                        class="text-muted d-flex align-items-center"
                        title={new Date(issue.added_on).toISOString()}
                    >
                        <div>Added by <span class="fw-bold">@{users[issue.user_id].username}</span> on {timestampToISODate(new Date(issue.added_on))}</div>
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
                    <div class="d-flex justify-content-end">
                        <div class="ms-1">Runs:</div>
                        {#each issue.runs as run, idx}
                            <a class="ms-1" href="/test_run/{run}">[{idx + 1}]</a>
                        {/each}
                    </div>
                {/if}
            </div>
        </div>
    </div>
</div>

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
                />
            </div>
            <div class="modal-body">
                <p>
                    Are you sure you want to remove <span class="fw-bold"
                        >{issue.repo}#{issue.issue_number}</span
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
                    on:click={deleteIssue}
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
    }

    .issue-open {
        color: #f4faff;
        background-color: #347d39;
    }

    .issue-closed {
        color: #f4faff;
        background-color: #8256d0;
    }


</style>
