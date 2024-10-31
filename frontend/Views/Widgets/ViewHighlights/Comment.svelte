<script lang="ts">
    import Fa from 'svelte-fa';
    import {faEdit, faTrash} from '@fortawesome/free-solid-svg-icons';
    import {createEventDispatcher} from 'svelte';
    import {getPicture} from "../../../Common/UserUtils";

    export let comment;
    export let currentUserId;
    export let action;
    export let highlight;
    export let users = {};

    let creator = users[comment.creator_id];
    let isArchived = action?.isArchived || highlight?.isArchived;
    let isEditing = false;
    let commentTimeStr = comment.createdAt.toLocaleDateString("en-CA") + " " + comment.createdAt.toLocaleTimeString("en-GB");

    const dispatch = createEventDispatcher();

    const updateContent = () => {
        dispatch('updateCommentContent', {comment, newContent: comment.content});
        isEditing = false;
    };
    const deleteComment = () => dispatch('deleteComment', {comment});
</script>

<li class="list-group-item py-1"  class:bg-light={isArchived}>
    <div class="align-items-center">
        {#if isEditing}
            <input type="text" class="form-control me-2" bind:value={comment.content}
                   on:keydown={(e) => { if(e.key === 'Enter') updateContent(); }}>
            <button class="btn btn-sm btn-primary me-2" on:click={updateContent}>Save</button>
            <button class="btn btn-sm btn-secondary me-2" on:click={() => isEditing = false}>Cancel</button>
        {:else}
            <div class="flex-fill d-inline-flex">
                <div class="img-profile me-2" style="background-image: url('{getPicture(creator?.picture_id)}');" data-bs-toggle="tooltip" title="{creator?.username}" />
                <small class="text-muted ms-2">{commentTimeStr}</small>
            </div>
        {/if}
        <div class="d-flex">
            <p class="mb-0 flex-grow-1">{comment.content}</p>
            {#if comment.creator_id === currentUserId && !isArchived}
            <button class="btn btn-sm btn-outline-secondary me-1" on:click={() => isEditing = !isEditing}>
                <Fa icon={faEdit}/>
            </button>
            <button class="btn btn-sm btn-outline-danger" on:click={deleteComment}>
                <Fa icon={faTrash}/>
            </button>
        {/if}
        </div>
    </div>
</li>
