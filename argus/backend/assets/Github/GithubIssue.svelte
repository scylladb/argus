<script>
    import { createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import { faGithub } from "@fortawesome/free-brands-svg-icons";
    import { faCheckCircle } from "@fortawesome/free-regular-svg-icons";
    import {
        faExclamationCircle,
        faTrash,
    } from "@fortawesome/free-solid-svg-icons";
    import { sendMessage } from "../Stores/AlertStore";
    import { userList } from "../Stores/UserlistSubscriber";

    const dispatch = createEventDispatcher();
    let users = {};
    $: users = $userList;
    const IssueColorMap = {
        open: "text-success",
        closed: "text-danger",
    };

    const IssueIcon = {
        open: faExclamationCircle,
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
        type: "issues",
        url: "https://github.com/",
        user_id: "",
        added_on: "Mon, 1 Jan 1970 9:00:00 GMT",
    };

    let deleting = false;

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

<div class="row m-2 border rounded p-2">
    <div class="col hstack">
        <div
            class="me-2 text-truncate"
            style="width: 20em;"
            title={issue.title}
        >
            <Fa icon={faGithub} /> <a href={issue.url}>{issue.title}</a>
        </div>
        <div class="text-muted me-auto">{issue.repo}#{issue.issue_number}</div>
        {#if Object.keys(users).length > 0}
            <div
                class="text-muted me-2"
                title={new Date(issue.added_on).toISOString()}
            >
                Added by {users[issue.user_id].username}
            </div>
        {/if}
        <div class="text-muted">
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
