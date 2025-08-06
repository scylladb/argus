<script lang="ts">
    import { run } from 'svelte/legacy';

    import { onDestroy, onMount } from "svelte";
    import Comment from "../Discussion/Comment.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    import { sendMessage } from "../Stores/AlertStore";
    import CommentEditor from "../Discussion/CommentEditor.svelte";

    let { testInfo, testRun } = $props();
    let fetchIntervalId;
    let suppressFetch = $state(false);
    let comments = $state([]);
    let users = $state({});
    let fetching = $state(false);
    let hideReplyButton = false;
    run(() => {
        users = $userList;
    });
    const newCommentTemplate = {
        id: "",
        message: "",
        release: testInfo.release.name,
        reactions: {},
        mentions: [],
        user_id: "",
        release_id: "",
        test_run_id: testRun.id,
        posted_at: new Date(),
    };

    let newCommentBody = $state(Object.assign({}, newCommentTemplate));

    const fetchComments = async function () {
        try {
            let apiResponse = await fetch(`/api/v1/run/${testRun.id}/comments`);
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                comments = apiJson.response;
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to fetch comments.\nMessage: ${error.response.arguments[0]}`,
                    "TestRunComments::fetchComments"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during comments fetch",
                    "TestRunComments::fetchComments"
                );
            }
        }
    };

    const handleCommentSubmit = async function (e) {
        let commentBody = e.detail;
        fetching = true;
        try {
            let apiResponse = await fetch(`/api/v1/test/${testInfo.test.id}/run/${testRun.id}/comments/submit`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    message: commentBody.message,
                    reactions: commentBody.reactions,
                    mentions: commentBody.mentions,
                }),
            });
            let apiJson = await apiResponse.json();
            console.log(apiJson);
            if (apiJson.status === "ok") {
                comments = apiJson.response;
                fetching = false;
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error during comment submission.\nMessage: ${error.response.arguments[0]}`,
                    "TestRunComments::handleCommentSubmit"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during comment submission",
                    "TestRunComments::handleCommentSubmit"
                );
            }
        } finally {
            newCommentBody = Object.assign({}, newCommentTemplate);
        }
    };

    const handleCommentUpdate = async function (e) {
        let commentBody = e.detail;
        suppressFetch = false;
        try {
            let apiResponse = await fetch(`/api/v1/test/${testInfo.test.id}/run/${testRun.id}/comment/${commentBody.id}/update`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    message: commentBody.message,
                    reactions: commentBody.reactions,
                    mentions: commentBody.mentions,
                }),
            });
            let apiJson = await apiResponse.json();
            console.log(apiJson);
            if (apiJson.status === "ok") {
                comments = apiJson.response;
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error during comment update.\nMessage: ${error.response.arguments[0]}`,
                    "TestRunComments::handleCommentUpdate"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during comment update.",
                    "TestRunComments::handleCommentUpdate"
                );
            }
        }
    };

    const handleCommentReply = function (e) {
        let author_id = e.detail.author;
        let author = users?.[author_id]?.username;
        let quotedMessage = e.detail.message.trim().replaceAll("&gt;", ">").replaceAll("&lt;", "<").split("\n").map((val) => `> ${val}`).join("\n");
        newCommentBody.message = `${author ? `@${author} posted:` : ""}${newCommentBody.message}\n${quotedMessage}\n`;
    };

    const handleCommentDelete = async function (e) {
        let commentBody = e.detail;
        try {
            let apiResponse = await fetch(`/api/v1/test/${testInfo.test.id}/run/${testRun.id}/comment/${commentBody.id}/delete`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
            });
            let apiJson = await apiResponse.json();
            console.log(apiJson);
            if (apiJson.status === "ok") {
                comments = apiJson.response;
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error during comment deletion.\nMessage: ${error.response.arguments[0]}`,
                    "TestRunComments::handleCommentDelete"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during release comment deletion.",
                    "TestRunComments::handleCommentDelete"
                );
            }
        }
    };

    onMount(() => {
        fetchComments();
        fetchIntervalId = setInterval(() => {
            if (suppressFetch) return;
            fetchComments();
        }, 60 * 1000);
    });

    onDestroy(() => {
        clearInterval(fetchIntervalId);
    });
</script>

<div class="container-fluid bg-editor">
    {#if Object.keys(users).length > 0}
        {#each comments as comment (comment.id)}
            <div class="row">
                <div class="col my-3">
                    <Comment
                        commentBody={comment}
                        {users}
                        {hideReplyButton}
                        on:commentDelete={handleCommentDelete}
                        on:commentUpdated={handleCommentUpdate}
                        on:commentEditing={() => (suppressFetch = true)}
                        on:commentReply={handleCommentReply}
                    />
                </div>
            </div>
        {:else}
            <div class="row">
                <div class="col text-center p-1 text-muted">
                    No comments yet.
                </div>
            </div>
        {/each}
    {:else}
        <div class="col m-1">
            <div class="text-muted text-center p-2 fs-4">
                <span class="spinner-grow"></span> Loading...
            </div>
        </div>
    {/if}
    <div class="row border-top">
        {#if !fetching}
            <div class="col mx-1 my-2">
                <CommentEditor
                    runId={testRun.id}
                    mode="post"
                    bind:commentBody={newCommentBody}
                    on:submitComment={handleCommentSubmit}
                />
            </div>
        {:else}
            <div class="col m-1">
                <div class="text-muted text-center p-2 fs-4">
                    <span class="spinner-grow"></span> Loading...
                </div>
            </div>
        {/if}
    </div>
</div>

<style>
    .bg-editor {
        background-color: #f2f2f2;
    }
</style>
