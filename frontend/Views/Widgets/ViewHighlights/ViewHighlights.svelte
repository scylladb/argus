<script lang="ts">
    import { run } from 'svelte/legacy';

    import {onMount} from "svelte";
    import Fa from "svelte-fa";
    import {faPlus, faChevronDown, faChevronRight, faChevronUp, faCheck} from "@fortawesome/free-solid-svg-icons";
    import {applicationCurrentUser} from "../../../argus";
    import {userList} from "../../../Stores/UserlistSubscriber";
    import HighlightItem from "./HighlightItem.svelte";
    import ActionItem from "./ActionItem.svelte";
    import CommentEditor from "../../../Discussion/CommentEditor.svelte";

    let { dashboardObject, settings } = $props();
    let index = settings.index;
    let redraw = $state(0);
    let users = $state({});

    interface Entry {
        id: string;
        view_id: string;
        type: "highlight" | "action";
        content: string;
        creator_id: string;
        createdAt: Date;
        group: string | null;
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

    let highlights: Entry[] = $state([]);
    let actionItems: Entry[] = $state([]);
    let showNewHighlight = $state(false);
    let showArchivedHighlights = $state(false);
    let showArchivedActionItems = $state(false);
    // let newHighlight = "";
    let newHighlightInput: HTMLInputElement;

    interface GroupState {
        showNewActionItem: boolean;
        collapsed: boolean;
        touched: boolean;
        isFullyCompleted: boolean;
    }

    let groupStates = $state<Record<string, GroupState>>({});
    let groupNames = $state<string[]>(["General"]);
    let showGroupModal = $state(false);
    let newGroupName = "";
    let groupCreationError = "";
    let isCreatingGroup = $state(false);

    let defaultGroupItems: string[] = settings.defaultGroupItems || [];

    run(() => {
        if (Object.keys(users).length === 0 && Object.keys($userList).length > 0) {
            users = $userList;
            redraw++
        }
    });

    onMount(async () => {
        const response = await fetch(`/api/v1/views/widgets/highlights?view_id=${dashboardObject.id}&index=${index}`);
        const data = await response.json();
        if (data.status === "ok") {
            highlights = data.response.highlights.map(parseEntry);
            actionItems = data.response.action_items.map(parseEntry);
            syncGroupStates();
        }
    });

    function parseEntry(data): Entry {
        const isAction = data.completed !== undefined;
        return {
            id: data.created_at.toString(),
            view_id: data.view_id,
            type: isAction ? "action" : "highlight",
            content: data.content,
            creator_id: data.creator_id,
            createdAt: new Date(data.created_at * 1000),
            group: isAction ? (data.group ?? "General") : (data.group ?? null),
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

    function sortGroups(names: Set<string>): string[] {
        return Array.from(names).sort((a, b) => {
            if (a === "General") return -1;
            if (b === "General") return 1;
            return a.localeCompare(b);
        });
    }

    function isGroupFullyCompleted(name: string): boolean {
        const items = getGroupItems(name, false);
        return items.length > 0 && items.every(item => item.isCompleted);
    }

    function getOrCreateGroupState(name: string): GroupState {
        if (groupStates[name]) {
            return groupStates[name];
        }
        return {
            showNewActionItem: false,
            collapsed: isGroupFullyCompleted(name),
            touched: false,
            isFullyCompleted: isGroupFullyCompleted(name),
        };
    }

    function syncGroupStates() {
        const names = new Set(actionItems.map(item => item.group || "General"));
        names.add("General");
        const sorted = sortGroups(names);
        const nextStates: Record<string, GroupState> = {};
        for (const name of sorted) {
            const previous = groupStates[name];
            const shouldCollapse = isGroupFullyCompleted(name);
            const isCompleted = isGroupFullyCompleted(name);

            if (!previous) {
                nextStates[name] = {
                    showNewActionItem: false,
                    collapsed: shouldCollapse,
                    touched: false,
                    isFullyCompleted: isCompleted,
                };
                continue;
            }

            let collapsed = previous.collapsed;
            let touched = previous.touched;

            if (shouldCollapse) {
                collapsed = true;
                touched = false;
            } else if (!previous.touched) {
                collapsed = false;
            }

            nextStates[name] = {
                showNewActionItem: previous.showNewActionItem,
                collapsed,
                touched,
                isFullyCompleted: isCompleted,
            };
        }
        groupStates = nextStates;
        groupNames = sorted;
        redraw++;
    }

    function getGroupItems(name: string, archived: boolean) {
        return actionItems.filter(item => (item.group || "General") === name && item.isArchived === archived);
    }

    function shouldShowActiveGroup(name: string): boolean {
        if (name === "General") {
            return true;
        }
        return getGroupItems(name, false).length > 0;
    }

    function toggleGroupEditor(name: string, show: boolean) {
        const state = getOrCreateGroupState(name);
        groupStates = {
            ...groupStates,
            [name]: {
                ...state,
                showNewActionItem: show,
            },
        };
        redraw++;
    }

    function toggleGroupCollapse(name: string) {
        const state = getOrCreateGroupState(name);
        groupStates = {
            ...groupStates,
            [name]: {
                ...state,
                collapsed: !state.collapsed,
                touched: true,
            },
        };
        redraw++;
    }

    function isGroupCollapsed(name: string): boolean {
        return groupStates[name]?.collapsed ?? isGroupFullyCompleted(name);
    }


    const addEntry = async (type: "highlight" | "action", content: string, group?: string) => {
        if (!content.trim()) return;
        const payload: Record<string, unknown> = {
            view_id: dashboardObject.id,
            index: index,
            content: content,
            is_task: type === "action",
        };
        if (type === "action") {
            payload.group = group && group !== "General" ? group : null;
        }
        const response = await fetch("/api/v1/views/widgets/highlights/create", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (data.status === "ok") {
            const newEntry = parseEntry(data.response);
            if (type === "action") {
                actionItems = [newEntry, ...actionItems];
                syncGroupStates();
            } else {
                highlights = [newEntry, ...highlights];
                showNewHighlight = false;
            }
        }
    };
    const handleHightlightCreate = function (e) {
        addEntry("highlight", e.detail.message);
    };

    const handleGroupActionItemCreate = async (group: string, message: string) => {
        if (!message.trim()) return;
        await addEntry("action", message, group);
        toggleGroupEditor(group, false);
    };

    const handleGroupActionItemCancel = (group: string) => {
        toggleGroupEditor(group, false);
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
            syncGroupStates();
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
            syncGroupStates();
        }
    };

    const handleSetAssignee = async (event) => {
        const actionItem = event.detail.action;
        const assignee = event.detail.assignee?.value || undefined;
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

    const handleCreateGroup = async () => {
        groupCreationError = "";
        const trimmedName = newGroupName.trim();
        if (!trimmedName) {
            groupCreationError = "Group name is required";
            redraw++;
            return;
        }
        if (defaultGroupItems.length === 0) {
            groupCreationError = "No template items configured. Configure it in Admin Panel.";
            redraw++;
            return;
        }
        isCreatingGroup = true;
        try {
            const response = await fetch("/api/v1/views/widgets/highlights/create_group", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    view_id: dashboardObject.id,
                    index: index,
                    name: trimmedName,
                    items: defaultGroupItems,
                }),
            });
            const data = await response.json();
            if (data.status === "ok") {
                const createdItems = data.response.map(parseEntry);
                actionItems = [...createdItems, ...actionItems];
                newGroupName = "";
                showGroupModal = false;
                syncGroupStates();
            } else {
                groupCreationError = data.message || "Failed to create group";
                redraw++;
            }
        } catch (error) {
            groupCreationError = "Failed to create group";
            redraw++;
        } finally {
            isCreatingGroup = false;
        }
    };

    run(() => {
        if (showNewHighlight && newHighlightInput) {
            newHighlightInput.focus();
        }
    });
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
                            <button class="btn w-100 text-start text-muted" onclick={() => showNewHighlight = true}>
                                <Fa icon={faPlus}/>
                                Add Highlight
                            </button>
                        {/if}
                    </li>
                </ul>
                {#if highlights.some(h => h.isArchived)}
                    <div class="mt-3">
                        <button class="btn w-100 text-start"
                                onclick={() => showArchivedHighlights = !showArchivedHighlights}>
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
            <div class="card-header d-flex justify-content-between align-items-center">
                <h2 class="h5 mb-0">Action Items</h2>
                <button class="btn btn-sm btn-outline-primary" onclick={() => { newGroupName = ""; groupCreationError = ""; showGroupModal = true; }}>
                    <Fa icon={faPlus}/>
                    <span class="ms-1">Create Group</span>
                </button>
            </div>
            <div class="card-body">
                <ul class="list-group">
                    {#each groupNames as groupName (groupName)}
                        {#if shouldShowActiveGroup(groupName)}
                            <li class="list-group-item fw-semibold d-flex align-items-center"
                                class:bg-success-subtle={groupStates[groupName]?.isFullyCompleted}
                                class:bg-body-secondary={!groupStates[groupName]?.isFullyCompleted}>
                                <button class="btn btn-link text-decoration-none text-reset d-flex align-items-center p-0 flex-grow-1"
                                        type="button"
                                        aria-expanded={!isGroupCollapsed(groupName)}
                                        onclick={() => toggleGroupCollapse(groupName)}>
                                    <Fa icon={isGroupCollapsed(groupName) ? faChevronRight : faChevronDown} class="me-2"/>
                                    <span>{groupName}</span>
                                </button>
                                {#if groupStates[groupName]?.isFullyCompleted}
                                    <Fa icon={faCheck} class="text-success ms-2"/>
                                {/if}
                            </li>
                            {#if !isGroupCollapsed(groupName)}
                                {#each getGroupItems(groupName, false) as action (action.id)}
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
                                    {#if groupStates[groupName]?.showNewActionItem}
                                        <div class="flex-grow-1">
                                            <CommentEditor
                                                    mode="post"
                                                    entryType="action item"
                                                    on:submitComment={(event) => handleGroupActionItemCreate(groupName, event.detail.message)}
                                                    on:cancelEditing={() => handleGroupActionItemCancel(groupName)}
                                            />
                                        </div>
                                    {:else}
                                        <button class="btn w-100 text-start text-muted" onclick={() => toggleGroupEditor(groupName, true)}>
                                            <Fa icon={faPlus}/>
                                            Add Action Item
                                        </button>
                                    {/if}
                                </li>
                            {/if}
                        {/if}
                    {/each}
                </ul>
                {#if actionItems.some(a => a.isArchived)}
                    <div class="mt-3">
                        <button class="btn w-100 text-start"
                                onclick={() => showArchivedActionItems = !showArchivedActionItems}>
                            <Fa icon={showArchivedActionItems ? faChevronUp : faChevronDown}/>
                            {showArchivedActionItems ? "Hide Archived Action Items" : "Show Archived Action Items"}
                        </button>
                        {#if showArchivedActionItems}
                            <ul class="list-group mt-2">
                                {#each groupNames as groupName (groupName)}
                                    {#if getGroupItems(groupName, true).length}
                                        <li class="list-group-item fw-semibold d-flex align-items-center"
                                            class:bg-success-subtle={groupStates[groupName]?.isFullyCompleted}
                                            class:bg-body-secondary={!groupStates[groupName]?.isFullyCompleted}>
                                            <button class="btn btn-link text-decoration-none text-reset d-flex align-items-center p-0 flex-grow-1"
                                                    type="button"
                                                    aria-expanded={!isGroupCollapsed(groupName)}
                                                    onclick={() => toggleGroupCollapse(groupName)}>
                                                <Fa icon={isGroupCollapsed(groupName) ? faChevronRight : faChevronDown} class="me-2"/>
                                                <span>{groupName}</span>
                                            </button>
                                            {#if groupStates[groupName]?.isFullyCompleted}
                                                <Fa icon={faCheck} class="text-success ms-2"/>
                                            {/if}
                                        </li>
                                        {#if !isGroupCollapsed(groupName)}
                                            {#each getGroupItems(groupName, true) as action (action.id)}
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
                                        {/if}
                                    {/if}
                                {/each}
                            </ul>
                        {/if}
                    </div>
                {/if}
            </div>
        </div>

        {#if showGroupModal}
            <div class="modal show d-block" tabindex="-1" role="dialog">
                <div class="modal-dialog" role="document">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Create Action Item Group</h5>
                            <button type="button" class="btn-close" aria-label="Close"
                                    onclick={() => { showGroupModal = false; groupCreationError = ""; }}></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <label class="form-label" for="group-name-input">Group name</label>
                                <input id="group-name-input" class="form-control" bind:value={newGroupName}
                                       placeholder="e.g. 2025.3.3" />
                            </div>
                            <p class="mb-1">The following action items will be created:</p>
                            <ul class="mb-0">
                                {#each defaultGroupItems as item}
                                    <li>{item}</li>
                                {/each}
                            </ul>
                            {#if groupCreationError}
                                <div class="alert alert-danger mt-3" role="alert">{groupCreationError}</div>
                            {/if}
                        </div>
                        <div class="modal-footer">
                            <button class="btn btn-secondary" onclick={() => { showGroupModal = false; groupCreationError = ""; }}>
                                Cancel
                            </button>
                            <button class="btn btn-primary" onclick={handleCreateGroup} disabled={isCreatingGroup}>
                                {isCreatingGroup ? "Creating..." : "Create Group"}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            <div class="modal-backdrop fade show"></div>
        {/if}
    {/key}
</div>

<style>
    :global(.no-bottom-margin *:last-child) {
    margin-bottom: 0;
}

</style>
