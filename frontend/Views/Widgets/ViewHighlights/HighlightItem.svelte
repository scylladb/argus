<script lang="ts">
    import Fa from 'svelte-fa';
    import {faArchive, faUndo, faComment, faEdit} from '@fortawesome/free-solid-svg-icons';
    import Comment from './Comment.svelte';
    import {createEventDispatcher} from 'svelte';
    import {getPicture} from "../../../Common/UserUtils";
    import CommentEditor from "../../../Discussion/CommentEditor.svelte";
    import { marked } from "marked";
    import {markdownRendererOptions} from "../../../markdownOptions";
    import {MarkdownUserMention} from "../../../Discussion/MarkedMentionExtension";

    let { highlight = $bindable(), currentUserId, users = {} } = $props();

    let creator = users[highlight.creator_id] || {};
    let isEditing = $state(false);
    let newComment = '';
    let showNewCommentEditor = $state(false);
    let newCommentBody = $state({
        id: "",
        message: "",
        release: "",
        reactions: {},
        mentions: [],
        user_id: currentUserId || "",
        release_id: "",
        test_run_id: "",
        posted_at: new Date(),
    });
    let commentBody = $state({
        id: '',
        message: highlight.content,
        release: '',
        reactions: {},
        mentions: [],
        user_id: '',
        release_id: '',
        test_run_id: '',
        posted_at: new Date(),
    });
    marked.use({
        extensions: [MarkdownUserMention]
    });
    const dispatch = createEventDispatcher();

    const toggleArchive = () => dispatch('toggleArchive', {highlight});
    const toggleComments = () => {
        highlight.showComments = !highlight.showComments;
        if (highlight.showComments && highlight.comments.length === 0) {
            dispatch('loadComments', {highlight});
        }
    };
    const addComment = () => {
        if (!newComment.trim()) return;
        dispatch('addComment', {highlight, content: newComment});
        newComment = '';
    };

    const handleCommentKeydown = (event: KeyboardEvent) => {
        if (event.key === 'Enter') addComment();
    };
    const handleCommentUpdate = (e: { detail: any }) => {
        commentBody.message = e.detail.message;
        isEditing = false;
        dispatch('updateContent', {highlight, newContent: commentBody.message});
    };

    const handleNewCommentSubmit = (event: { detail: any }) => {
        const commentData = event.detail;
        dispatch('addComment', {highlight, content: commentData.message});
        newCommentBody.message = "";
        showNewCommentEditor = false;
    };
</script>

<li class="list-group-item" class:bg-light={highlight.isArchived}>
    <div class="d-flex justify-content-between align-items-center">
        {#if !isEditing}
            <div class="img-profile me-2" style="background-image: url('{getPicture(creator?.picture_id)}');"
                 data-bs-toggle="tooltip"
                 title="{creator?.username}"></div>
            <div class="d-flex align-items-center flex-grow-1 no-bottom-margin-p markdown-body">
                <span class="no-bottom-margin">{@html marked.parse(highlight.content, markdownRendererOptions)}</span>
            </div>
            <div class="d-flex align-items-center">
                <small class="text-muted me-2">{highlight.createdAt.toLocaleDateString("en-CA")}</small>
                <button class="btn btn-sm btn-outline-secondary me-1" onclick={toggleComments}>
                    <Fa icon={faComment}/>
                    <span class="ms-1">{highlight.comments_count}</span>
                </button>
                {#if !highlight.isArchived}
                    {#if highlight.creator_id === currentUserId}
                        <button class="btn btn-sm btn-outline-secondary me-1" onclick={() => isEditing = !isEditing}>
                            <Fa icon={faEdit}/>
                        </button>
                    {/if}
                {/if}
                <button class="btn btn-sm btn-outline-secondary" onclick={toggleArchive}>
                    <Fa icon={highlight.isArchived ? faUndo : faArchive}/>
                </button>
            </div>
        {:else}
            <div class="flex-grow-1">
                <CommentEditor
                        commentBody={Object.assign({}, commentBody)}
                        mode="edit"
                        entryType="highlight"
                        on:submitComment={handleCommentUpdate}
                        on:cancelEditing={() => (isEditing = false)}
                />
            </div>
        {/if}
    </div>
    {#if highlight.showComments}
        <div class="mt-2 col-md-10">
            <ul class="list-group list-group-flush">
                {#each highlight.comments as comment (comment.id)}
                    <Comment {comment} {currentUserId} action={null} {highlight} {users} on:deleteComment on:updateCommentContent/>
                {/each}
            </ul>
            {#if !highlight.isArchived}
                {#if showNewCommentEditor}
                    <div class="mt-2">
                        <CommentEditor
                            commentBody={newCommentBody}
                            mode="post"
                            entryType="comment"
                            on:submitComment={handleNewCommentSubmit}
                            on:cancelEditing={() => (showNewCommentEditor = false)}
                        />
                    </div>
                {:else}
                    <button class="btn btn-outline-primary w-100 mt-2" onclick={() => showNewCommentEditor = true}>
                        Add a comment
                    </button>
                {/if}
            {/if}
        </div>
    {/if}
</li>
