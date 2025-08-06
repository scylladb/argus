<script lang="ts">
    import Comment from "../Discussion/Comment.svelte";
    import CommentEditor from "../Discussion/CommentEditor.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { userList } from "../Stores/UserlistSubscriber";
    let users = $userList;
    let { supportData } = $props();
    let replying = $state(false);
    let fetching = $state(false);
    let replyUser = $state("");

    const newCommentTemplate = {
        id: "",
        message: "",
        release: "",
        reactions: {},
        mentions: [],
        user_id: "",
        release_id: "",
        test_run_id: supportData.test_run_id,
        posted_at: new Date(),
    };

    let newCommentBody = $state();

    const handleReplyButton = function (e) {
        newCommentBody = Object.assign({}, newCommentTemplate);
        let authorId = e.detail.author;
        let authorUsername = users?.[authorId]?.username;
        replyUser = authorUsername;
        let quotedMessage = e.detail.message
            .trim()
            .replaceAll("&gt;", ">")
            .replaceAll("&lt;", "<")
            .split("\n")
            .map((val) => `> ${val}`)
            .join("\n");
        newCommentBody.message = `${authorUsername ? `@${authorUsername} posted:` : ""}${
            newCommentBody.message
        }\n${quotedMessage}\n`;
        replying = true;
    };

    const handleCommentSubmit = async function (e) {
        let commentBody = e.detail;
        fetching = true;
        try {
            let apiResponse = await fetch(
                `/api/v1/test/${supportData.test_id}/run/${supportData.test_run_id}/comments/submit`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        message: commentBody.message,
                        reactions: commentBody.reactions,
                        mentions: commentBody.mentions,
                    }),
                }
            );
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                fetching = false;
                replying = false;
                sendMessage("success", "Reply submitted!");
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage("error", `API Error during comment submission.\nMessage: ${error.response.arguments[0]}`);
            } else {
                sendMessage("error", "A backend error occurred during comment submission");
            }
        } finally {
            newCommentBody = Object.assign({}, newCommentTemplate);
        }
    };
</script>

<Comment commentBody={supportData} {users} hideUserActions={true} hideReplyButton={!supportData.test_id} on:commentReply={handleReplyButton} />
{#if replying}
    <div class="reply-modal">
        <div class="d-flex align-items-center justify-content-center p-4">
            <div class="rounded bg-white p-4 h-50 position-relative">
                {#if fetching}
                    <div class="position-absolute d-flex align-items-center justify-content-center fetching-blocker">
                        <span class="spinner-grow"></span>
                        <div class="ms-1">Replying...</div>
                    </div>
                {/if}
                <div class="mb-2 d-flex border-bottom pb-2">
                    <h5>Replying to <span class="fw-bold">{replyUser}</span></h5>
                    <div class="ms-auto">
                        <button class="btn btn-close" onclick={() => (replying = false)}></button>
                    </div>
                </div>
                <CommentEditor
                    runId={supportData.test_run_id}
                    mode="post"
                    bind:commentBody={newCommentBody}
                    on:submitComment={handleCommentSubmit}
                />
            </div>
        </div>
    </div>
{/if}

<style>
    .h-50 {
        width: 50%;
    }
    .reply-modal {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        overflow-y: scroll;
        background-color: rgba(0, 0, 0, 0.55);
        z-index: 9999;
    }

    .fetching-blocker {
        left: 0px;
        top: 0px;
        height: 100%;
        width: 100%;
        background-color: rgba(0.3, 0.3, 0.3, 0.5);
        z-index: 99999;
        color: white;
    }
</style>
