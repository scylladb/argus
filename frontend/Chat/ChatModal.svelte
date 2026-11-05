<script lang="ts">
    import { onDestroy, onMount, tick } from "svelte";
    import { SvelteSet } from "svelte/reactivity";
    import Fa from "svelte-fa";
    import { faBookmark, faCircle, faClockRotateLeft, faComments, faGauge, faTrash } from "@fortawesome/free-solid-svg-icons";
    import { fetchJson } from "../Common/ApiUtils";
    import type { User } from "../Common/UserTypes";
    import { getPicture } from "../Common/UserUtils";
    import { sendMessage } from "../Stores/AlertStore";
    import { userList } from "../Stores/UserlistSubscriber.js";
    import ChatComposer from "./ChatComposer.svelte";
    import ChatContextStats from "./ChatContextStats.svelte";
    import ChatMemories from "./ChatMemories.svelte";
    import ChatMessage from "./ChatMessage.svelte";
    import { chatBase, postJson } from "./chatApi";
    import { connectChat } from "./chatEvents";
    import { displayName } from "./chatFormat";
    import { applyEvent } from "./chatState";
    import { activePath, splitTurns } from "./chatTree";
    import type { ChatNode, Conversation, EntityType, Memory, ServerEvent, Started } from "./types";

    interface Props {
        entityType: EntityType;
        entityId: string;
        entityName: string;
        isAdmin?: boolean;
        onClose: () => void;
    }

    let { entityType, entityId, entityName, isAdmin = false, onClose }: Props = $props();

    const POLL_MS = 3000;

    let conversation = $state<Conversation | null>(null);
    let memories = $state<Memory[]>([]);
    let presence = $state<string[]>([]);
    let live = $state(false);
    let loadError = $state("");
    let side = $state<"memories" | "history" | "context">("memories");
    let thread = $state<HTMLElement | undefined>();
    let confirmingClear = $state(false);
    const watched = new SvelteSet<string>();

    const base = $derived(chatBase(entityType, entityId));
    const users = $derived($userList as Record<string, User>);
    const path = $derived(conversation ? activePath(conversation.nodes, conversation.head) : []);
    const turns = $derived(splitTurns(path));
    const busy = $derived(Boolean(conversation?.busy));
    const disabledReason = $derived(
        !conversation
            ? "Loading the conversation…"
            : !conversation.configured
              ? "No chat model is configured. An administrator picks one in the Admin Panel, under Chat."
              : "",
    );

    let stopEvents = () => {};
    let poller: ReturnType<typeof setInterval> | undefined;
    let previousOverflow = "";

    const fail = (error: unknown) =>
        sendMessage("error", error instanceof Error ? error.message : String(error), "Chat");

    const load = async () => {
        try {
            conversation = await fetchJson<Conversation>(base);
            loadError = "";
        } catch (error) {
            loadError = error instanceof Error ? error.message : String(error);
        }
    };

    const nearBottom = () => !thread || thread.scrollHeight - thread.scrollTop - thread.clientHeight < 160;

    const scrollToBottom = async (force = false) => {
        if (!thread || !(force || nearBottom())) return;
        await tick();
        thread.scrollTop = thread.scrollHeight;
    };

    const watch = (node: ChatNode) => {
        if (node.status === "streaming") watched.add(node.node);
    };

    const handleEvent = (event: ServerEvent) => {
        if (event.type === "memory") {
            memories = event.memories;
            return;
        }
        if (event.type === "presence") {
            presence = event.users;
            return;
        }
        if (event.type === "snapshot") {
            conversation = event.conversation;
            return;
        }
        if (!conversation) return;
        const follow = nearBottom();
        if (event.type === "node") watch(event.node);
        if (event.type === "delta") watched.add(event.node);
        conversation = applyEvent(conversation, event);
        if (follow) scrollToBottom(true);
    };

    const applyStarted = (started: Started) => {
        if (!conversation) return;
        for (const node of [started.user_node, started.assistant_node]) {
            if (node) {
                watch(node);
                conversation = applyEvent(conversation, { type: "node", node });
            }
        }
        conversation = { ...conversation, head: started.assistant_node.node,
                         busy: { node: started.assistant_node.node, user_id: started.assistant_node.user_id ?? "",
                                 since: started.assistant_node.created_at } };
        scrollToBottom(true);
    };

    const start = async (path: string, body?: unknown): Promise<boolean> => {
        try {
            applyStarted(await postJson<Started>(`${base}/${path}`, body));
            return true;
        } catch (error) {
            fail(error);
            return false;
        }
    };

    const replace = async (path: string, body?: unknown) => {
        try {
            conversation = await postJson<Conversation>(`${base}/${path}`, body);
        } catch (error) {
            fail(error);
        }
    };

    const decideCard = async (node: string, decision: "confirm" | "dismiss" | "refresh") => {
        try {
            const card = await postJson<ChatNode>(`${base}/actions/${node}/${decision}`);
            if (conversation) conversation = applyEvent(conversation, { type: "node", node: card });
        } catch (error) {
            fail(error);
        }
    };

    const clear = async () => {
        confirmingClear = false;
        try {
            conversation = await postJson<Conversation>(base, undefined, "DELETE");
        } catch (error) {
            fail(error);
        }
    };

    const stop = async () => {
        try {
            await postJson(`${base}/stop`);
        } catch (error) {
            fail(error);
        }
    };

    const handleKey = (event: KeyboardEvent) => {
        if (event.key === "Escape") onClose();
    };

    onMount(async () => {
        previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        stopEvents = connectChat(`${base}/events`, { onEvent: handleEvent, onLive: (value) => (live = value) });
        poller = setInterval(() => {
            if (!live) load();
        }, POLL_MS);
        await load();
        try {
            memories = await fetchJson<Memory[]>(`${base}/memories`);
        } catch (error) {
            fail(error);
        }
        scrollToBottom(true);
    });

    onDestroy(() => {
        stopEvents();
        clearInterval(poller);
        document.body.style.overflow = previousOverflow;
    });
</script>

<svelte:window onkeydown={handleKey} />

<div class="chat-overlay" role="presentation">
    <div class="chat-panel rounded bg-white shadow d-flex flex-column" role="dialog" aria-modal="true"
         aria-label="Chat about {entityName}">
        <header class="d-flex align-items-center gap-2 px-3 py-2 border-bottom flex-wrap">
            <Fa icon={faComments} />
            <h2 class="h6 mb-0">Chat · {entityName}</h2>
            {#if conversation?.model}
                <span class="badge text-bg-light">{conversation.model.model}</span>
            {/if}
            <span class="small d-inline-flex align-items-center gap-1"
                  class:text-success={live} class:text-body-secondary={!live}
                  title={live ? "Following live" : `Not live; refreshing every ${POLL_MS / 1000} s`}>
                <Fa icon={faCircle} size="xs" /> {live ? "Live" : "Reconnecting"}
            </span>
            <div class="ms-auto d-flex align-items-center gap-1" aria-label="People in this chat">
                {#each presence as userId (userId)}
                    <img class="img-profile" src={getPicture(users[userId]?.picture_id)}
                         alt={displayName(userId, users)} title="{displayName(userId, users)} has this chat open" />
                {/each}
            </div>
            {#if isAdmin}
                {#if confirmingClear}
                    <span class="small">Clear the whole conversation for everyone? Memories stay.</span>
                    <button type="button" class="btn btn-sm btn-danger" onclick={clear}>Clear</button>
                    <button type="button" class="btn btn-sm btn-link text-body-secondary text-decoration-none" onclick={() => (confirmingClear = false)}>
                        Cancel
                    </button>
                {:else}
                    <button type="button" class="btn btn-sm btn-link text-danger text-decoration-none" disabled={busy}
                            title={busy ? "Wait for the answer to finish" : "Admins only"}
                            onclick={() => (confirmingClear = true)}>
                        <Fa icon={faTrash} /> Clear chat
                    </button>
                {/if}
            {/if}
            <button type="button" class="btn btn-close" aria-label="Close" onclick={onClose}></button>
        </header>

        <div class="chat-body d-flex flex-column flex-lg-row gap-2 p-2 bg-light-one flex-grow-1">
            <section class="d-flex flex-column gap-2 flex-grow-1 main-column">
                <div class="thread flex-grow-1 d-flex flex-column gap-3 p-2" bind:this={thread}>
                    {#if loadError && !conversation}
                        <div class="alert alert-danger">{loadError}</div>
                    {:else if !conversation}
                        <div class="text-body-secondary"><span class="spinner-border spinner-border-sm"></span> Loading…</div>
                    {:else if turns.length === 0}
                        <div class="text-body-secondary text-center my-auto">
                            <p class="mb-1">No questions yet.</p>
                            <p class="small mb-0">Try "what failed on the latest release candidate?" or "rerun the
                                failed upgrade tests on gce".</p>
                        </div>
                    {:else}
                        {#each turns as turn (turn.opener.node)}
                            <ChatMessage
                                {turn}
                                nodes={conversation.nodes}
                                {users}
                                {memories}
                                assistant={conversation.assistant}
                                initiallyExpanded={turn.answers.some((node) => watched.has(node.node))}
                                onSetHead={(node) => replace("head", { node })}
                                onConfirm={(node) => decideCard(node, "confirm")}
                                onDismiss={(node) => decideCard(node, "dismiss")}
                                onRefresh={(node) => decideCard(node, "refresh")}
                            />
                        {/each}
                    {/if}
                </div>
                <ChatComposer
                    {entityType}
                    {disabledReason}
                    {busy}
                    canRetry={path.some((node) => node.role === "user")}
                    canUndo={path.length > 0}
                    onSend={(content) => start("messages", { content })}
                    onStop={stop}
                    onRetry={() => start("regenerate")}
                    onUndo={() => replace("undo")}
                />
            </section>

            <aside class="side-column rounded bg-white shadow-sm d-flex flex-column">
                <ul class="nav nav-underline px-3 pt-1 border-bottom" role="tablist">
                    <li class="nav-item">
                        <button type="button" class="nav-link" class:active={side === "memories"} role="tab"
                                aria-selected={side === "memories"} onclick={() => (side = "memories")}>
                            <Fa icon={faBookmark} /> Memories <span class="badge rounded-pill text-bg-light">{memories.length}</span>
                        </button>
                    </li>
                    <li class="nav-item">
                        <button type="button" class="nav-link" class:active={side === "history"} role="tab"
                                aria-selected={side === "history"} onclick={() => (side = "history")}>
                            <Fa icon={faClockRotateLeft} /> History
                        </button>
                    </li>
                    <li class="nav-item">
                        <button type="button" class="nav-link" class:active={side === "context"} role="tab"
                                aria-selected={side === "context"} onclick={() => (side = "context")}>
                            <Fa icon={faGauge} /> Context
                        </button>
                    </li>
                </ul>
                <div class="side-scroll flex-grow-1 p-2 d-flex flex-column">
                    <div class="side-inset rounded bg-light-one shadow-sm p-2 d-flex flex-column gap-2 flex-grow-1">
                        {#if side === "context"}
                            {#if conversation}
                                <ChatContextStats context={conversation.context} model={conversation.model} {busy}
                                                  empty={path.length === 0} onCompact={() => start("compact")} />
                            {/if}
                        {:else}
                            <ChatMemories {base} tab={side === "history" ? "history" : "list"} {memories}
                                          scopes={conversation?.scopes ?? []} {users}
                                          onChange={(fresh) => (memories = fresh)} />
                        {/if}
                    </div>
                </div>
            </aside>
        </div>
    </div>
</div>

<style>
    .chat-overlay {
        position: fixed;
        inset: 0;
        background-color: rgba(0, 0, 0, 0.55);
        z-index: 1060;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 1rem;
    }
    .chat-panel {
        width: min(1400px, 100%);
        height: min(92vh, 100%);
        overflow: hidden;
    }
    .chat-body {
        min-height: 0;
    }
    .main-column {
        min-width: 0;
        min-height: 0;
    }
    .thread {
        overflow-y: auto;
        min-height: 12rem;
    }
    .side-column {
        flex: 0 0 22rem;
        min-height: 0;
        overflow: hidden;
    }
    .side-scroll {
        overflow-y: auto;
        min-height: 0;
    }
    .side-column .nav-link {
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        font-size: 0.9rem;
    }
    @media (max-width: 991.98px) {
        .side-column {
            flex-basis: 16rem;
        }
    }
</style>
