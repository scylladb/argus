<script lang="ts">
    import Fa from 'svelte-fa';
    import {faEdit, faTrash} from '@fortawesome/free-solid-svg-icons';
    import {createEventDispatcher} from 'svelte';
    import {getPicture} from "../../../Common/UserUtils";
    import CommentEditor from "../../../Discussion/CommentEditor.svelte";
    import { marked } from "marked";
    import { markdownRendererOptions } from "../../../markdownOptions";

    interface Props {
        comment: any;
        currentUserId: string;
        action: any;
        highlight: any;
        users?: Record<string, any>;
    }

    let {
        comment = $bindable(),
        currentUserId,
        action,
        highlight,
        users = {}
    }: Props = $props();

    let creator = comment.creator_id ? users[comment.creator_id] || {} : {};
    let isArchived = action?.isArchived || highlight?.isArchived;
    let isEditing = $state(false);
    let commentTimeStr = comment.createdAt.toLocaleDateString("en-CA") + " " + comment.createdAt.toLocaleTimeString("en-GB");
    let commentBody = {
        id: comment.id || "",
        message: comment.content || "",
        release: "",
        reactions: {},
        mentions: [],
        user_id: comment.creator_id || "",
        release_id: "",
        test_run_id: "",
        posted_at: comment.createdAt || new Date(),
    };

    const dispatch = createEventDispatcher();

    const updateContent = (event: { detail?: any }) => {
        const updatedComment = event?.detail || commentBody;
        comment.content = updatedComment.message;
        dispatch('updateCommentContent', {comment, newContent: comment.content});
        isEditing = false;
    };
    const deleteComment = () => dispatch('deleteComment', {comment});
</script>

<li class="list-group-item py-1" class:bg-light={isArchived}>
    {#if isEditing}
        <div class="flex-grow-1">
            <CommentEditor
                commentBody={commentBody}
                mode="edit"
                entryType="comment"
                on:submitComment={updateContent}
                on:cancelEditing={() => isEditing = false}
            />
        </div>
    {:else}
        <div class="d-flex">
            <div class="flex-fill d-inline-flex align-items-start">
                <div class="img-profile me-2" style="background-image: url('{getPicture(creator?.picture_id)}');" data-bs-toggle="tooltip" title="{creator?.username}"></div>
                <small class="text-muted ms-2">{commentTimeStr}</small>
            </div>
        </div>
        <div class="d-flex justify-content-between align-items-start mt-1">
            <div class="mb-0 flex-grow-1 markdown-body">
                {@html marked.parse(comment.content, markdownRendererOptions)}
            </div>
            {#if comment.creator_id === currentUserId && !isArchived}
            <div class="d-flex align-items-start ms-2">
                <button class="btn btn-sm btn-outline-secondary me-1" onclick={() => isEditing = !isEditing}>
                    <Fa icon={faEdit}/>
                </button>
                <button class="btn btn-sm btn-outline-danger" onclick={deleteComment}>
                    <Fa icon={faTrash}/>
                </button>
            </div>
            {/if}
        </div>
    {/if}
</li>
