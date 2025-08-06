<script lang="ts">
    import * as marked from "marked";
    import Fa from "svelte-fa";
    import { faEdit, faArrowAltCircleLeft, faTrashAlt } from "@fortawesome/free-regular-svg-icons";
    import humanizeDuration from "humanize-duration";
    import CommentEditor from "./CommentEditor.svelte";
    import UserProfile from "./UserProfile.svelte";
    import { timestampToISODate } from "../Common/DateUtils";
    import { createEventDispatcher, onDestroy, onMount } from "svelte";
    import { markdownRendererOptions } from "../markdownOptions";
    import { MarkdownUserMention } from "./MarkedMentionExtension";
    import { applicationCurrentUser } from "../argus";
    interface Props {
        users?: any;
        commentBody?: any;
        hideReplyButton?: boolean;
        hideUserActions?: boolean;
    }

    let {
        users = {},
        commentBody = {
        id: "",
        message: "",
        release: "",
        reactions: {},
        mentions: [],
        user_id: "",
        release_id: "",
        test_run_id: "",
        posted_at: new Date(),
    },
        hideReplyButton = false,
        hideUserActions = false
    }: Props = $props();
    marked.use({
        extensions: [MarkdownUserMention]
    });

    const dispatch = createEventDispatcher();
    let editing = $state(false);
    let deleting = $state(false);
    let commentDate = new Date(commentBody.posted_at * 1000);
    let dateIntervalId;
    let now = $state(new Date());

    const getUser = function () {
        return users[commentBody.user_id];
    };

    const handleCommentUpdate = function (e) {
        editing = false;
        dispatch("commentUpdated", e.detail);
    };

    onMount(() => {
        dateIntervalId = setInterval(() => {
            now = new Date();
        }, 3 * 1000);
    });

    onDestroy(() => {
        clearInterval(dateIntervalId);
    });
</script>

<div class="rounded shadow-sm overflow-hidden position-relative">
    {#if deleting}
        <div class="position-absolute w-100 h-100 overflow-hidden">
            <div
                class="bg-blur text-muted text-center p-2 fs-4 h-100 d-flex align-items-center"
            >
                <div class="flex-fill">
                    <span class="spinner-grow"></span> Deleting...
                </div>
            </div>
        </div>
    {/if}
    <div
        class=" bg-light p-2 d-flex align-items-center"
    >
        <div>
            <UserProfile user={getUser()} />
        </div>
        <div
            class="ms-2 border shadow-sm bg-light p-1 rounded fs-7 text-dark"
            title="{timestampToISODate(commentBody.posted_at * 1000)} UTC+0"
        >
            {#if (now.getTime() - commentDate.getTime()) > 60000}
                {humanizeDuration(now - commentDate, {
                    round: true,
                    units: ["y", "mo", "w", "d", "h", "m"],
                    largest: 1,
                })} ago
            {:else}
                just now
            {/if}
        </div>
        {#if !hideReplyButton}
            <div class="ms-auto">
                <button
                    class="btn btn-light bg-editor"
                    title="Quote Reply"
                    onclick={() => (dispatch("commentReply", { message: commentBody.message, author: commentBody.user_id }))}
                >
                    <Fa icon={faArrowAltCircleLeft} />
                </button>
            </div>
        {/if}
        {#if applicationCurrentUser.id == commentBody.user_id && !hideUserActions}
            <div class:ms-1={!hideReplyButton} class:ms-auto={hideReplyButton}>
                <button
                    class="btn btn-light bg-editor"
                    title="Edit"
                    onclick={() => {
                        editing = true;
                        dispatch("commentEditing");
                    }}
                >
                    <Fa icon={faEdit} />
                </button>
                <button
                    class="btn btn-light bg-editor"
                    title="Delete"
                    data-bs-toggle="modal"
                    data-bs-target="#modalCommentConfirmDelete-{commentBody.id}"
                >
                    <Fa icon={faTrashAlt} />
                </button>
            </div>
        {/if}
    </div>
    <div>
        {#if editing}
            <CommentEditor
                commentBody={Object.assign({}, commentBody)}
                mode="edit"
                on:submitComment={handleCommentUpdate}
                on:cancelEditing={() => (editing = false)}
            />
        {:else}
            <div class="p-2 rounded bg-light">
                <div class="border rounded p-2 markdown-body">
                    {@html marked.parse(commentBody.message, markdownRendererOptions)}
                </div>
            </div>
        {/if}
    </div>
</div>

<div
    class="modal"
    tabindex="-1"
    id="modalCommentConfirmDelete-{commentBody.id}"
>
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Deleting a comment</h5>
                <button
                    type="button"
                    class="btn-close"
                    data-bs-dismiss="modal"
                    aria-label="Close"
></button>
            </div>
            <div class="modal-body">
                <p>Are you sure you want to remove this comment?</p>
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
                    onclick={() => {
                        deleting = true;
                        dispatch("commentDelete", commentBody);
                    }}
                >
                    Yes
                </button>
            </div>
        </div>
    </div>
</div>

<style>
    .fs-7 {
        font-size: 0.8em;
    }

    .border-lightish {
        border-color: lightsteelblue !important;
    }

    .bg-editor {
        background-color: #f2f2f2;
    }

    .bg-blur {
        background-color: #ffffff00;
        backdrop-filter: blur(4px);
    }
</style>
