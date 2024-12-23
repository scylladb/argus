<script lang="ts">
    import Fa from 'svelte-fa';
    import {faArchive, faUndo, faComment, faEdit} from '@fortawesome/free-solid-svg-icons';
    import Comment from './Comment.svelte';
    import {createEventDispatcher} from 'svelte';
    import {getPicture} from "../../../Common/UserUtils";
    import AssigneeSelector from "../../../Common/AssigneeSelector.svelte";
    import CommentEditor from "../../../Discussion/CommentEditor.svelte";
    import * as marked from "marked";
    import {MarkdownUserMention} from "../../../Discussion/MarkedMentionExtension";
    import {markdownRendererOptions} from "../../../markdownOptions";

    export let action;
    export let currentUserId;
    export let users = {};

    let isEditing = false;
    let newComment = '';
    let creator = users[action.creator_id];
    let assignee_id = action.assignee_id;
    let isArchived = action.isArchived;
    const dispatch = createEventDispatcher();
    let commentBody = {
        id: '',
        message: action.content,
        release: '',
        reactions: {},
        mentions: [],
        user_id: '',
        release_id: '',
        test_run_id: '',
        posted_at: new Date(),
    };
    marked.use({
        extensions: [MarkdownUserMention]
    });
    const toggleArchive = () => dispatch('toggleArchive', {action});
    const toggleComments = () => {
        action.showComments = !action.showComments;
        if (action.showComments && action.comments.length === 0) {
            dispatch('loadComments', {action});
        }
    };
    const updateContent = (e) => {
        commentBody.message = e.detail.message;
        isEditing = false;
        dispatch('updateContent', {action, newContent: commentBody.message});
    };
    const addComment = () => {
        if (!newComment.trim()) return;
        dispatch('addComment', {action, content: newComment});
        newComment = '';
    };
    const handleCommentKeydown = (event: KeyboardEvent) => {
        if (event.key === 'Enter') addComment();
    };
    const toggleComplete = () => dispatch('toggleComplete', {action});
    const handleAssignee = (e) => dispatch('assigneeSelected', {action, assignee: e.detail});
</script>

<li class="list-group-item" class:bg-light={isArchived}>
    <div class="d-flex justify-content-between align-items-center">
        {#if !isEditing}
            <div class="img-profile me-2" style="background-image: url('{getPicture(creator?.picture_id)}');" data-bs-toggle="tooltip"
                 title="{creator?.username}"/>
            <div class="d-flex align-items-center flex-grow-1">
                <input id="checkbox-{action.id}" class="form-check-input me-2 mt-0" type="checkbox" disabled={isArchived}
                       bind:checked={action.isCompleted} on:change={toggleComplete}>
                <label class="form-check-label no-bottom-margin"
                       for="checkbox-{action.id}">{@html marked.parse(action.content, markdownRendererOptions)}
                </label>
            </div>
            <div class="d-flex align-items-center">
                <small class="text-muted me-2">{action.createdAt.toLocaleDateString("en-CA")}</small>
                <div class="select-width ">
                    <AssigneeSelector {assignee_id} on:select={handleAssignee} disabled={isArchived} on:clear={handleAssignee}/>
                </div>
                <button class="btn btn-sm btn-outline-secondary mx-1" on:click={toggleComments}>
                    <Fa icon={faComment}/>
                    <span class="ms-1">{action.comments_count}</span>
                </button>
                {#if !action.isArchived}
                    {#if action.creator_id === currentUserId}
                        <button class="btn btn-sm btn-outline-secondary me-1" on:click={() => isEditing = !isEditing}>
                            <Fa icon={faEdit}/>
                        </button>
                    {/if}
                {/if}
                <button class="btn btn-sm btn-outline-secondary" on:click={toggleArchive}>
                    <Fa icon={action.isArchived ? faUndo : faArchive}/>
                </button>
            </div>
        {:else}
            <div class="flex-grow-1">
                <CommentEditor
                        commentBody={Object.assign({}, commentBody)}
                        mode="edit"
                        entryType="action item"
                        on:submitComment={updateContent}
                        on:cancelEditing={() => (isEditing = false)}
                />
            </div>
        {/if}
        {#if action.showComments}
            <div class="mt-2 col-md-10">
                <ul class="list-group list-group-flush">
                    {#each action.comments as comment (comment.id)}
                        <Comment {comment} {currentUserId} {action} on:deleteComment on:updateCommentContent/>
                    {/each}
                </ul>
                {#if !action.isArchived}
                    <div class="input-group mt-2">
                        <input type="text" class="form-control" placeholder="Add a comment" bind:value={newComment}
                               on:keydown={handleCommentKeydown}>
                        <button class="btn btn-outline-primary" on:click={addComment}>Add</button>
                    </div>
                {/if}
            </div>
        {/if}
</li>

<style>
    .select-width {
        /*needed due flex-grow-1 of action item content */
        min-width: 200px !important;
    }
</style>
