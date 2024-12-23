<script lang="ts">
    import {onMount} from "svelte";
    import Fa from "svelte-fa";
    import {faPlus, faChevronDown, faChevronUp} from "@fortawesome/free-solid-svg-icons";
    import {applicationCurrentUser} from "../../../argus";
    import {userList} from "../../../Stores/UserlistSubscriber";
    import HighlightItem from "./HighlightItem.svelte";
    import ActionItem from "./ActionItem.svelte";
    import CommentEditor from "../../../Discussion/CommentEditor.svelte";

    export let dashboardObject;
    export let settings;
    let index = settings.index;
    let redraw = 0;
    let users = {};

    interface Entry {
        id: string;
        view_id: string;
        type: "highlight" | "action";
        content: string;
        creator_id: string;
        createdAt: Date;
        isCompleted?: boolean;
        assignee_id?: string;
        comments_count: number;
        comments: Comment[];
        isArchived: boolean;
        showComments: boolean;
    }

    interface Comment {
        id: string;
        view_id: string;
        highlight_created_at: number;
        content: string;
        creator_id: string;
        createdAt: Date;
    }

    let highlights: Entry[] = [];
    let actionItems: Entry[] = [];
    let showNewHighlight = false;
    let showNewActionItem = false;
    let showArchivedHighlights = false;
    let showArchivedActionItems = false;
    let newHighlight = "";
    let newActionItem = "";
    let newActionInput: HTMLInputElement;
    let newHighlightInput: HTMLInputElement;

    $: users = $userList;
    $: if (users) {
        redraw++;
    }

    onMount(async () => {
        const response = await fetch(`/api/v1/views/widgets/highlights?view_id=${dashboardObject.id}&index=${index}`);
        const data = await response.json();
        if (data.status === "ok") {
            highlights = data.response.highlights.map(parseEntry);
            actionItems = data.response.action_items.map(parseEntry);
        }
    });

    function parseEntry(data): Entry {
        return {
            id: data.created_at.toString(),
            view_id: data.view_id,
            type: data.completed === undefined ? "highlight" : "action",
            content: data.content,
            creator_id: data.creator_id,
            createdAt: new Date(data.created_at * 1000),
            isArchived: data.archived_at !== 0,
            isCompleted: data.completed,
            assignee_id: data.assignee_id,
            comments_count: data.comments_count,
            comments: [],
            showComments: false,
        };
    }

    function parseComment(data): Comment {
        return {
            id: data.created_at.toString(),
            view_id: data.view_id,
            highlight_created_at: data.highlight_created_at,
            content: data.content,
            creator_id: data.creator_id,
            createdAt: new Date(data.created_at * 1000),
        };
    }


    const addEntry = async (type: "highlight" | "action", content: string) => {
        if (!content.trim()) return;
        const response = await fetch("/api/v1/views/widgets/highlights/create", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                view_id: dashboardObject.id,
                index: index,
                content: content,
                is_task: type === "action",
            }),
        });
        const data = await response.json();
        if (data.status === "ok") {
            const newEntry = parseEntry(data.response);
            if (type === "action") {
                actionItems = [newEntry, ...actionItems];
                newActionItem = "";
                showNewActionItem = false;
            } else {
                highlights = [newEntry, ...highlights];
                newHighlight = "";
                showNewHighlight = false;
            }
        }
    };
    const handleHightlightCreate = function (e) {
        addEntry("highlight", e.detail.message);
    };
    const handleActionItemCreate = function (e) {
        addEntry("action", e.detail.message);
    };

    const handleToggleArchive = async (event) => {
        const entry = event.detail.highlight || event.detail.action;
        const endpoint = entry.isArchived ? "/api/v1/views/widgets/highlights/unarchive" : "/api/v1/views/widgets/highlights/archive";
        const response = await fetch(endpoint, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                view_id: entry.view_id,
                index: index,
                created_at: entry.createdAt.getTime() / 1000,
            }),
        });
        const data = await response.json();
        if (data.status === "ok") {
            entry.isArchived = !entry.isArchived;
            redraw++;
        }
    };

    const handleLoadComments = async (event) => {
        const entry = event.detail.highlight || event.detail.action;
        if (entry.comments.length === 0) {
            const response = await fetch(`/api/v1/views/widgets/highlights/comments?view_id=${entry.view_id}&index=${index}&created_at=${entry.createdAt.getTime() / 1000}`);
            const data = await response.json();
            if (data.status === "ok") {
                entry.comments = data.response.map(parseComment);
                entry.showComments = true;
                redraw++;
            }
        }
    };

    const handleUpdateEntry = async (event) => {
        const entry = event.detail.highlight || event.detail.action;
        const newContent = event.detail.newContent;
        if (!newContent.trim()) return;
        const response = await fetch("/api/v1/views/widgets/highlights/update", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                view_id: entry.view_id,
                index: index,
                created_at: entry.createdAt.getTime() / 1000,
                content: newContent,
            }),
        });
        const data = await response.json();
        if (data.status === "ok") {
            entry.content = data.response.content;
            redraw++;
        }
    };

    const handleAddComment = async (event) => {
        const entry = event.detail.highlight || event.detail.action;
        const content = event.detail.content;
        if (!content.trim()) return;
        const response = await fetch("/api/v1/views/widgets/highlights/comments/create", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                view_id: entry.view_id,
                index: index,
                highlight_created_at: entry.createdAt.getTime() / 1000,
                content: content,
            }),
        });
        const data = await response.json();
        if (data.status === "ok") {
            const comment = parseComment(data.response);
            entry.comments = [...entry.comments, comment];
            entry.comments_count++;
            redraw++;
        }
    };

    const handleDeleteComment = async (event) => {
        const comment = event.detail.comment;
        const entry = highlights.find(h => h.comments.some(c => c.id === comment.id)) ||
            actionItems.find(a => a.comments.some(c => c.id === comment.id));
        if (!entry) return;
        const response = await fetch("/api/v1/views/widgets/highlights/comments/delete", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                view_id: comment.view_id,
                index: index,
                highlight_created_at: comment.highlight_created_at,
                created_at: comment.createdAt.getTime() / 1000,
            }),
        });
        const data = await response.json();
        if (data.status === "ok") {
            entry.comments = entry.comments.filter(c => c.id !== comment.id);
            entry.comments_count--;
            redraw++;
        }
    };

    const handleUpdateComment = async (event) => {
        const comment = event.detail.comment;
        const newContent = event.detail.newContent;
        if (!newContent.trim()) return;
        const entry = highlights.find(h => h.comments.some(c => c.id === comment.id)) ||
            actionItems.find(a => a.comments.some(c => c.id === comment.id));
        if (!entry) return;
        const response = await fetch("/api/v1/views/widgets/highlights/comments/update", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                view_id: comment.view_id,
                index: index,
                highlight_created_at: comment.highlight_created_at,
                created_at: comment.createdAt.getTime() / 1000,
                content: newContent,
            }),
        });
        const data = await response.json();
        if (data.status === "ok") {
            const idx = entry.comments.findIndex(c => c.id === comment.id);
            if (idx !== -1) {
                entry.comments[idx].content = data.response.content;
                redraw++;
            }
        }
    };

    const handleToggleComplete = async (event) => {
        const actionItem = event.detail.action;
        const response = await fetch("/api/v1/views/widgets/highlights/set_completed", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                view_id: actionItem.view_id,
                index: index,
                created_at: actionItem.createdAt.getTime() / 1000,
                completed: actionItem.isCompleted,
            }),
        });
        const data = await response.json();
        if (data.status === "ok") {
            actionItem.isCompleted = data.response.completed;
            redraw++;
        }
    };

    const handleSetAssignee = async (event) => {
        const actionItem = event.detail.action || event.detail.action;
        const assignee = event.detail.assignee?.value || undefined;
        console.log("handling assignee", assignee);
        const response = await fetch("/api/v1/views/widgets/highlights/set_assignee", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                view_id: actionItem.view_id,
                index: index,
                created_at: actionItem.createdAt.getTime() / 1000,
                assignee_id: assignee,
            }),
        });
        const data = await response.json();
        if (data.status === "ok") {
            actionItem.assignee_id = data.response.assignee_id;
            redraw++;
        }
    };

    $: if (showNewActionItem && newActionInput) {
        newActionInput.focus();
    }

    $: if (showNewHighlight && newHighlightInput) {
        newHighlightInput.focus();
    }
</script>


<div class="col-md-12 col-lg-10 col-xl-9 col-xxl-8">
    {#key redraw}
        <div class="card mb-4">
            <div class="card-header">
                <h2 class="h5 mb-0">Highlights</h2>
            </div>
            <div class="card-body">
                <ul class="list-group">
                    {#each highlights.filter(h => !h.isArchived) as highlight (highlight.id)}
                        <HighlightItem {highlight} currentUserId={applicationCurrentUser.id} {users}
                                       on:toggleArchive={handleToggleArchive}
                                       on:loadComments={handleLoadComments}
                                       on:updateContent={handleUpdateEntry}
                                       on:addComment={handleAddComment}
                                       on:deleteComment={handleDeleteComment}
                                       on:updateCommentContent={handleUpdateComment}
                        />
                    {/each}
                    <li class="list-group-item">
                        {#if showNewHighlight}
                            <div class="flex-grow-1">
                                <CommentEditor
                                        mode="post"
                                        entryType="highlight"
                                        on:submitComment={handleHightlightCreate}
                                        on:cancelEditing={() => (showNewHighlight = false)}
                                />
                            </div>
                        {:else}
                            <button class="btn w-100 text-start text-muted" on:click={() => showNewHighlight = true}>
                                <Fa icon={faPlus}/>
                                Add Highlight
                            </button>
                        {/if}
                    </li>
                </ul>
                {#if highlights.some(h => h.isArchived)}
                    <div class="mt-3">
                        <button class="btn w-100 text-start"
                                on:click={() => showArchivedHighlights = !showArchivedHighlights}>
                            <Fa icon={showArchivedHighlights ? faChevronUp : faChevronDown}/>
                            {showArchivedHighlights ? "Hide Archived Highlights" : "Show Archived Highlights"}
                        </button>
                        {#if showArchivedHighlights}
                            <ul class="list-group mt-2">
                                {#each highlights.filter(h => h.isArchived) as highlight (highlight.id)}
                                    <HighlightItem {highlight} currentUserId={applicationCurrentUser.id} {users}
                                                   on:toggleArchive={handleToggleArchive}
                                                   on:loadComments={handleLoadComments}
                                                   on:updateContent={handleUpdateEntry}
                                                   on:addComment={handleAddComment}
                                                   on:deleteComment={handleDeleteComment}
                                                   on:updateCommentContent={handleUpdateComment}
                                    />
                                {/each}
                            </ul>
                        {/if}
                    </div>
                {/if}
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <h2 class="h5 mb-0">Action Items</h2>
            </div>
            <div class="card-body">
                <ul class="list-group">
                    {#each actionItems.filter(a => !a.isArchived) as action (action.id)}
                        <ActionItem {action} currentUserId={applicationCurrentUser.id} {users}
                                    on:toggleArchive={handleToggleArchive}
                                    on:loadComments={handleLoadComments}
                                    on:updateContent={handleUpdateEntry}
                                    on:addComment={handleAddComment}
                                    on:deleteComment={handleDeleteComment}
                                    on:updateCommentContent={handleUpdateComment}
                                    on:toggleComplete={handleToggleComplete}
                                    on:assigneeSelected={handleSetAssignee}
                        />
                    {/each}
                    <li class="list-group-item">
                        {#if showNewActionItem}
                            <div class="flex-grow-1">
                                <CommentEditor
                                        mode="post"
                                        entryType="action item"
                                        on:submitComment={handleActionItemCreate}
                                        on:cancelEditing={() => (showNewActionItem = false)}
                                />
                            </div>
                        {:else}
                            <button class="btn w-100 text-start text-muted" on:click={() => showNewActionItem = true}>
                                <Fa icon={faPlus}/>
                                Add Action Item
                            </button>
                        {/if}
                    </li>
                </ul>
                {#if actionItems.some(a => a.isArchived)}
                    <div class="mt-3">
                        <button class="btn w-100 text-start"
                                on:click={() => showArchivedActionItems = !showArchivedActionItems}>
                            <Fa icon={showArchivedActionItems ? faChevronUp : faChevronDown}/>
                            {showArchivedActionItems ? "Hide Archived Action Items" : "Show Archived Action Items"}
                        </button>
                        {#if showArchivedActionItems}
                            <ul class="list-group mt-2">
                                {#each actionItems.filter(a => a.isArchived) as action (action.id)}
                                    <ActionItem {action} currentUserId={applicationCurrentUser.id} {users}
                                                on:toggleArchive={handleToggleArchive}
                                                on:loadComments={handleLoadComments}
                                                on:updateContent={handleUpdateEntry}
                                                on:addComment={handleAddComment}
                                                on:deleteComment={handleDeleteComment}
                                                on:updateCommentContent={handleUpdateComment}
                                                on:toggleComplete={handleToggleComplete}
                                    />
                                {/each}
                            </ul>
                        {/if}
                    </div>
                {/if}
            </div>
        </div>
    {/key}
</div>

<style>
    :global(.no-bottom-margin *:last-child) {
    margin-bottom: 0;
}

</style>
