<script lang="ts">
    import Fa from "svelte-fa";
    import { faChevronLeft, faChevronRight, faCodeBranch, faCompress } from "@fortawesome/free-solid-svg-icons";
    import type { User } from "../Common/UserTypes";
    import { getPicture } from "../Common/UserUtils";
    import AssistantAvatar from "./AssistantAvatar.svelte";
    import ChatActionCard from "./ChatActionCard.svelte";
    import { ago, displayName, preview } from "./chatFormat";
    import { alternativesOf, type Turn } from "./chatTree";
    import { renderMarkdown } from "./markdown";
    import type { AssistantIdentity, ChatNode, Memory } from "./types";

    interface Props {
        turn: Turn;
        nodes: ChatNode[];
        users: Record<string, User>;
        memories: Memory[];
        assistant?: AssistantIdentity | null;
        initiallyExpanded?: boolean;
        onSetHead: (node: string) => Promise<void>;
        onConfirm: (node: string) => Promise<void>;
        onDismiss: (node: string) => Promise<void>;
        onRefresh?: (node: string) => Promise<void>;
        onAdjust?: (node: string, testId: string, overrides: Record<string, string>) => Promise<string | null>;
        forkNode?: string | null;
        onFork?: (node: string) => Promise<void>;
    }

    let { turn, nodes, users, memories, assistant = null, initiallyExpanded = false, onSetHead, onConfirm, onDismiss,
          onRefresh, onAdjust, forkNode = null, onFork }: Props = $props();

    let expandedByUser = $state<boolean | null>(null);

    const opener = $derived(turn.opener);
    const answers = $derived(turn.answers);
    const last = $derived(answers.at(-1));
    const streaming = $derived(answers.some((node) => node.status === "streaming"));
    const expanded = $derived(expandedByUser ?? (initiallyExpanded || streaming));
    const text = $derived(answers.map((node) => node.content).filter(Boolean).join("\n\n"));
    const reasoning = $derived(answers.map((node) => node.reasoning).filter(Boolean).join("\n\n"));
    const alternatives = $derived(turn.firstAnswer ? alternativesOf(nodes, turn.firstAnswer) : null);
    const usedMemories = $derived.by(() => {
        const snapshot = turn.firstAnswer?.memory_snapshot ?? [];
        return snapshot.map((entry) => ({
            entry,
            memory: memories.find((memory) => memory.id === entry.memory_id),
        }));
    });
    const openerUser = $derived(opener.user_id ? users[opener.user_id] : undefined);
    const afterCompaction = $derived(
        nodes.some((node) => node.node === opener.parent && node.role === "summary" && node.status === "streaming"),
    );

    const compactionProgress = (node: ChatNode) => {
        const words = node.content.trim() ? node.content.trim().split(/\s+/).length : 0;
        if (words) return `${words} word${words === 1 ? "" : "s"} written`;
        return node.reasoning ? "thinking it over" : "waiting for the model";
    };
</script>

<article class="turn d-flex flex-column gap-1">
    {#if opener.role === "summary"}
        {@const compacting = opener.status === "streaming"}
        <details class="compaction small text-body-secondary" open={compacting}>
            <summary>
                <Fa icon={faCompress} />
                {#if compacting}
                    <span class="badge text-bg-info d-inline-flex align-items-center gap-1"><span
                        class="badge-spinner spinner-border" aria-hidden="true"></span>Compacting</span>
                    {opener.auto ? "the context automatically before the next answer" : "the context"} ·
                    {compactionProgress(opener)}
                {:else if opener.status === "error" || opener.status === "stopped"}
                    {opener.auto ? "The automatic compaction" : "The compaction"}
                    {opener.status === "error" ? "failed" : "stopped"} {ago(opener.created_at)}; the answers use the
                    whole conversation
                {:else}
                    Context compacted {opener.auto ? "automatically" : `by ${displayName(opener.user_id, users)}`}
                    {ago(opener.created_at)}
                {/if}
            </summary>
            {#if opener.content}
                <div class="markdown-body mt-1 p-2 rounded bg-white">{@html renderMarkdown(opener.content)}</div>
            {/if}
            {#if opener.error}<div class="text-danger mt-1">{opener.error}</div>{/if}
        </details>
    {:else if opener.role === "user"}
        <div class="question d-flex gap-2 align-items-start">
            <img class="img-profile flex-shrink-0 mt-1" src={getPicture(openerUser?.picture_id)} alt="" />
            <div class="flex-grow-1 min-w-0">
                <div class="small text-body-secondary">
                    <span class="fw-semibold text-body">{displayName(opener.user_id, users)}</span>
                    <span title={opener.created_at}>{ago(opener.created_at)}</span>
                </div>
                <div class="markdown-body question-text">{@html renderMarkdown(opener.content)}</div>
            </div>
        </div>
    {/if}

    {#if answers.length}
        <div class="answer rounded bg-white shadow-sm p-2 ms-4">
            <div class="d-flex align-items-center gap-2 small text-body-secondary flex-wrap">
                <AssistantAvatar {assistant} size={22} />
                <span class="fw-semibold text-body">{assistant?.name ?? "Assistant"}</span>
                {#if last?.model_name}<span>{last.model_name}</span>{/if}
                {#if streaming}
                    <span class="badge text-bg-info d-inline-flex align-items-center gap-1"><span class="badge-spinner spinner-border" aria-hidden="true"></span>Answering</span>
                {:else if last?.status === "error"}
                    <span class="badge text-bg-danger">Failed</span>
                {:else if last?.status === "stopped"}
                    <span class="badge text-bg-secondary">Stopped</span>
                {/if}
                {#if alternatives && alternatives.siblings.length > 1}
                    <span class="d-inline-flex align-items-center gap-1" aria-label="Answers to this question">
                        <button
                            type="button"
                            class="btn btn-sm btn-link p-0"
                            aria-label="Previous answer"
                            disabled={alternatives.index <= 0 || streaming}
                            onclick={() => onSetHead(alternatives.siblings[alternatives.index - 1].node)}
                        >
                            <Fa icon={faChevronLeft} />
                        </button>
                        <span>{alternatives.index + 1}/{alternatives.siblings.length}</span>
                        <button
                            type="button"
                            class="btn btn-sm btn-link p-0"
                            aria-label="Next answer"
                            disabled={alternatives.index >= alternatives.siblings.length - 1 || streaming}
                            onclick={() => onSetHead(alternatives.siblings[alternatives.index + 1].node)}
                        >
                            <Fa icon={faChevronRight} />
                        </button>
                    </span>
                {/if}
                {#if forkNode && onFork && !streaming}
                    <button type="button" class="btn btn-sm btn-link text-body-secondary text-decoration-none p-0 ms-auto"
                            title="Ask the next question from here, on a new branch; the later messages stay on theirs"
                            onclick={() => forkNode && onFork?.(forkNode)}>
                        <Fa icon={faCodeBranch} /> Fork
                    </button>
                {/if}
                <button
                    type="button"
                    class="btn btn-sm btn-link p-0"
                    class:ms-auto={!(forkNode && onFork && !streaming)}
                    aria-expanded={expanded}
                    onclick={() => (expandedByUser = !expanded)}
                >
                    {expanded ? "Collapse" : "Show answer"}
                </button>
            </div>

            {#if expanded}
                {#if text}
                    <div class="markdown-body mt-1">{@html renderMarkdown(text)}</div>
                {:else if streaming}
                    <div class="text-body-secondary small mt-1">
                        {afterCompaction ? "Waiting for the compaction to finish…" : "Waiting for the model…"}
                    </div>
                {/if}
            {:else}
                <button type="button" class="preview btn btn-link text-start text-body p-0 mt-1 w-100"
                        onclick={() => (expandedByUser = true)}>
                    {preview(text) || "No text"}
                </button>
            {/if}

            {#if last?.error}
                <div class="alert alert-danger py-1 px-2 small mt-1 mb-0">{last.error}</div>
            {/if}

            {#if expanded && (turn.tools.length || reasoning || usedMemories.length)}
                <div class="d-flex flex-column gap-1 mt-2 small">
                    {#if turn.tools.length}
                        <details>
                            <summary>Used {turn.tools.length} tool{turn.tools.length === 1 ? "" : "s"}</summary>
                            <ul class="list-unstyled mb-0">
                                {#each turn.tools as tool (tool.node)}
                                    {@const call = answers.flatMap((node) => node.tool_calls)
                                        .find((entry) => entry.id === tool.tool_call_id)}
                                    <li class="py-1 border-bottom">
                                        <span class="font-monospace fw-semibold" class:text-danger={tool.status === "error"}
                                            >{tool.tool_name}</span
                                        >
                                        {#if call}<code class="ms-1">{call.arguments}</code>{/if}
                                        <div class="tool-result font-monospace text-body-secondary">{tool.content}</div>
                                    </li>
                                {/each}
                            </ul>
                        </details>
                    {/if}
                    {#if reasoning}
                        <details>
                            <summary>Reasoning</summary>
                            <div class="reasoning text-body-secondary">{reasoning}</div>
                        </details>
                    {/if}
                    {#if usedMemories.length}
                        <details>
                            <summary>Context used: {usedMemories.length} memor{usedMemories.length === 1 ? "y" : "ies"}</summary>
                            <ul class="mb-0 ps-3">
                                {#each usedMemories as { entry, memory } (entry.memory_id)}
                                    <li>
                                        {#if memory}
                                            {memory.content}
                                            {#if memory.revision !== entry.revision}
                                                <span class="badge text-bg-light">changed since</span>
                                            {/if}
                                        {:else}
                                            <span class="text-body-secondary">A memory deleted since</span>
                                        {/if}
                                    </li>
                                {/each}
                            </ul>
                        </details>
                    {/if}
                </div>
            {/if}
        </div>
    {/if}

    {#each turn.actions as action (action.node)}
        <div class="ms-4">
            <ChatActionCard node={action} {users} {onConfirm} {onDismiss} {onRefresh} {onAdjust} />
        </div>
    {/each}
</article>

<style>
    .badge-spinner {
        width: 0.75em;
        height: 0.75em;
        border-width: 0.15em;
    }
    .turn :global(.markdown-body) {
        background-color: transparent;
        font-size: 0.9375rem;
    }
    .answer :global(.markdown-body) {
        font-size: 1.0625rem;
    }
    .question-text :global(p:last-child),
    .answer :global(.markdown-body p:last-child) {
        margin-bottom: 0;
    }
    .preview {
        display: -webkit-box;
        -webkit-line-clamp: 3;
        line-clamp: 3;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-decoration: none;
        font-size: 1rem;
    }
    .tool-result {
        font-size: 0.75rem;
        max-height: 8rem;
        overflow: auto;
        white-space: pre-wrap;
        word-break: break-all;
    }
    .reasoning {
        white-space: pre-wrap;
        max-height: 16rem;
        overflow: auto;
    }
    .min-w-0 {
        min-width: 0;
    }
</style>
