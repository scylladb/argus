<script lang="ts">
    import Fa from "svelte-fa";
    import {
        faArrowUpRightFromSquare,
        faCheck,
        faMagnifyingGlass,
        faPlay,
        faSliders,
        faXmark,
    } from "@fortawesome/free-solid-svg-icons";
    import type { User } from "../Common/UserTypes";
    import { ago, displayName } from "./chatFormat";
    import { renderMarkdown } from "./markdown";
    import StartParamsEditor from "./StartParamsEditor.svelte";
    import type { ActionResult, ChatAction, ChatNode } from "./types";

    interface Props {
        node: ChatNode;
        users: Record<string, User>;
        onConfirm: (node: string) => Promise<void>;
        onDismiss: (node: string) => Promise<void>;
        onRefresh?: (node: string) => Promise<void>;
        onAdjust?: (node: string, testId: string, overrides: Record<string, string>) => Promise<string | null>;
    }

    let { node, users, onConfirm, onDismiss, onRefresh, onAdjust }: Props = $props();

    const REFRESH_MS = 30_000;
    const ZEUS_BADGES: Record<string, string> = {
        queued: "text-bg-secondary",
        processing: "text-bg-info",
        completed: "text-bg-success",
        failed: "text-bg-danger",
    };

    let working = $state(false);
    let openParams = $state<Record<string, boolean>>({});
    let editing = $state<string | null>(null);

    const action = $derived(node.action as ChatAction);
    const tests = $derived(action.proposal.tests ?? []);
    const runs = $derived(action.proposal.runs ?? []);
    const zeusOpen = $derived(
        action.kind === "zeus_investigation" && action.state === "done" &&
            action.results.some((result) => result.task_id && ["queued", "processing"].includes(result.status ?? "")),
    );
    const title = $derived.by(() => {
        switch (action.kind) {
            case "execute_tests":
                return `Start ${tests.length} test${tests.length === 1 ? "" : "s"}`;
            case "link_issue":
                return "Link an issue";
            case "zeus_investigation":
                return `Queue ${runs.length} Zeus investigation${runs.length === 1 ? "" : "s"}`;
            case "edit_plan":
                return `Edit the plan ${action.proposal.plan}`;
            case "mcp_call":
                return `Call ${action.proposal.tool} on ${action.proposal.server}`;
            default:
                return "Unlink an issue";
        }
    });

    const decide = async (handler: (node: string) => Promise<void>) => {
        working = true;
        try {
            await handler(node.node);
        } finally {
            working = false;
        }
    };

    $effect(() => {
        if (!zeusOpen || !onRefresh) return;
        onRefresh(node.node);
        const timer = setInterval(() => onRefresh(node.node), REFRESH_MS);
        return () => clearInterval(timer);
    });

    const runLink = (result: ActionResult) =>
        result.build_system_id && result.build_number ? `/test/${result.build_system_id}/${result.build_number}` : null;
</script>

{#if action.kind === "zeus_report"}
    <section class="action-card rounded shadow-sm bg-white p-2 mt-2 small">
        <header class="d-flex align-items-center gap-2 flex-wrap mb-1">
            <span class="fw-semibold"><Fa icon={faMagnifyingGlass} /> Zeus report</span>
            <span class="font-monospace text-truncate">{action.proposal.test}</span>
            {#if action.proposal.build_number}<span class="text-body-secondary">#{action.proposal.build_number}</span>{/if}
            <a class="ms-auto text-nowrap" href={action.proposal.url} target="_blank" rel="noopener">
                Open run <Fa icon={faArrowUpRightFromSquare} />
            </a>
        </header>
        <div class="text-body-secondary mb-1">
            {action.proposal.author?.name ?? "Zeus"} · {ago(action.proposal.posted_at)}
        </div>
        <details open>
            <summary>Report</summary>
            <div class="markdown-body zeus-report mt-1 p-2 rounded bg-light-one">
                {@html renderMarkdown(action.proposal.report ?? "")}
            </div>
        </details>
    </section>
{:else if action.kind === "show_run"}
    <a class="run-card rounded shadow-sm bg-white p-2 mt-2 d-flex align-items-center gap-2 small text-decoration-none
              text-body" href={action.proposal.url} target="_blank" rel="noopener">
        <span class="font-monospace text-truncate">{action.proposal.test}</span>
        {#if action.proposal.build_number}<span class="text-body-secondary">#{action.proposal.build_number}</span>{/if}
        {#if action.proposal.status}<span class="badge text-bg-light">{action.proposal.status}</span>{/if}
        {#if action.proposal.version}<span class="text-body-secondary text-nowrap">{action.proposal.version}</span>{/if}
        <span class="ms-auto text-primary text-nowrap">Open run <Fa icon={faArrowUpRightFromSquare} /></span>
    </a>
{:else}
<div class="action-card rounded shadow-sm bg-white p-2 mt-2" class:pending={action.state === "pending"}>
    <div class="d-flex align-items-center gap-2 mb-1">
        <span class="fw-semibold">{title}</span>
        {#if action.state === "pending"}
            <span class="badge text-bg-warning">Waiting for confirmation</span>
        {:else if action.state === "running"}
            <span class="badge text-bg-info d-inline-flex align-items-center gap-1"><span class="badge-spinner spinner-border" aria-hidden="true"></span>Running</span>
        {:else if action.state === "done"}
            <span class="badge text-bg-success">Done</span>
        {:else}
            <span class="badge text-bg-secondary">Dismissed</span>
        {/if}
    </div>

    {#if action.kind === "execute_tests"}
        {#if tests.length}
            <ul class="list-unstyled mb-1 small">
                {#each tests as test (test.test_id)}
                    {@const result = action.results.find((entry) => entry.build_system_id === test.build_system_id)}
                    <li class="py-1 border-bottom">
                        <div class="d-flex flex-wrap align-items-center gap-1">
                            <span class="font-monospace">{test.test}</span>
                            {#each Object.entries(test.overrides) as [name, value] (name)}
                                <span class="badge text-bg-primary">{name}={value}</span>
                            {/each}
                            <span class="ms-auto d-inline-flex gap-2">
                                {#if action.state === "pending" && onAdjust}
                                    <button type="button" class="btn btn-link btn-sm p-0"
                                            title="Change this test's parameters before it starts"
                                            onclick={() => (editing = editing === test.test_id ? null : test.test_id)}>
                                        <Fa icon={faSliders} /> Edit parameters
                                    </button>
                                {/if}
                                <button
                                    type="button"
                                    class="btn btn-link btn-sm p-0"
                                    onclick={() => (openParams[test.test_id] = !openParams[test.test_id])}
                                >
                                    {openParams[test.test_id] ? "Hide parameters" : "All parameters"}
                                </button>
                            </span>
                        </div>
                        {#if editing === test.test_id && onAdjust}
                            <StartParamsEditor {test} onSave={(testId, overrides) => onAdjust(node.node, testId, overrides)}
                                               onClose={() => (editing = null)} />
                        {/if}
                        {#if result}
                            {#if result.error}
                                <div class="text-danger">Did not start: {result.error}</div>
                            {:else if runLink(result)}
                                <a href={runLink(result)} target="_blank" rel="noopener">Run #{result.build_number}</a>
                            {:else}
                                <span class="text-body-secondary">Queued (item {result.queue_item})</span>
                            {/if}
                        {/if}
                        {#if openParams[test.test_id]}
                            <table class="table table-sm mb-0 mt-1 params">
                                <tbody>
                                    {#each Object.entries(test.params) as [name, value] (name)}
                                        <tr class:table-primary={name in test.overrides}>
                                            <td class="font-monospace">{name}</td>
                                            <td class="font-monospace text-break">{value ?? ""}</td>
                                        </tr>
                                    {/each}
                                </tbody>
                            </table>
                        {/if}
                    </li>
                {/each}
            </ul>
        {/if}
        {#if action.rejected.length}
            <div class="small text-danger">
                <div class="fw-semibold">Left out</div>
                <ul class="mb-1 ps-3">
                    {#each action.rejected as rejected (rejected.test)}
                        <li><span class="font-monospace">{rejected.test}</span>: {rejected.reason}</li>
                    {/each}
                </ul>
            </div>
        {/if}
    {:else if action.kind === "zeus_investigation"}
        {#if action.proposal.question}
            <div class="small text-body-secondary mb-1">Question: {action.proposal.question}</div>
        {/if}
        <ul class="list-unstyled mb-1 small">
            {#each runs as run (run.run_id)}
                {@const result = action.results.find((entry) => entry.run_id === run.run_id)}
                <li class="py-1 border-bottom">
                    <div class="d-flex flex-wrap align-items-center gap-1">
                        <a class="font-monospace" href={run.url} target="_blank" rel="noopener">{run.test}</a>
                        <span class="text-body-secondary">{run.status}{run.version ? ` · ${run.version}` : ""}</span>
                        {#if result?.status}
                            <span class="badge ms-auto {ZEUS_BADGES[result.status] ?? 'text-bg-secondary'}">{result.status}</span>
                        {/if}
                    </div>
                    {#if result?.error}
                        <div class="text-danger">{result.error}</div>
                    {/if}
                    {#if result?.response}
                        <details class="mt-1">
                            <summary>Zeus report</summary>
                            <div class="markdown-body zeus-report mt-1 p-2 rounded bg-light-one">
                                {@html renderMarkdown(result.response)}
                            </div>
                        </details>
                    {/if}
                </li>
            {/each}
        </ul>
        {#if action.rejected.length}
            <div class="small text-danger">
                <div class="fw-semibold">Left out</div>
                <ul class="mb-1 ps-3">
                    {#each action.rejected as rejected (rejected.test)}
                        <li><span class="font-monospace">{rejected.test}</span>: {rejected.reason}</li>
                    {/each}
                </ul>
            </div>
        {/if}
        {#if action.state === "done" && action.refreshed_at}
            <div class="small text-body-secondary">
                Checked with Zeus {ago(action.refreshed_at)}{zeusOpen ? "; checking every 30 s while this chat is open" : ""}
            </div>
        {/if}
    {:else if action.kind === "edit_plan"}
        <ul class="small mb-1 ps-3 plan-changes">
            {#each action.proposal.summary ?? [] as line, index (index)}
                <li class:text-success={line.startsWith("+ ")} class:text-danger={line.startsWith("- ")}>{line}</li>
            {/each}
        </ul>
        {#each action.results.filter((entry) => entry.error) as result, index (index)}
            <div class="small text-danger">{result.error}</div>
        {/each}
    {:else if action.kind === "mcp_call"}
        <pre class="small rounded bg-light-one p-2 mb-1 arguments">{JSON.stringify(action.proposal.arguments ?? {}, null, 2)}</pre>
        {#each action.results as result, index (index)}
            {#if result.error}
                <div class="small text-danger">{result.error}</div>
            {:else}
                <details class="small" open>
                    <summary>Result</summary>
                    <pre class="rounded bg-light-one p-2 mb-0 mt-1 mcp-result">{result.text}</pre>
                </details>
            {/if}
        {/each}
    {:else}
        <div class="small">
            {#if action.kind === "link_issue"}
                <a href={action.proposal.issue_url} target="_blank" rel="noopener">{action.proposal.issue_url}</a>
            {:else}
                <span class="fw-semibold">{action.proposal.issue_key ?? action.proposal.issue_id}</span>
            {/if}
            on run <a href={action.proposal.run_url} target="_blank" rel="noopener"
                >{action.proposal.run_id?.slice(0, 8)}</a
            >
            {#each action.results.filter((entry) => entry.error) as result, index (index)}
                <div class="text-danger">{result.error}</div>
            {/each}
        </div>
    {/if}

    <div class="d-flex align-items-center gap-2 mt-1 small">
        {#if action.state === "pending"}
            <button
                type="button"
                class="btn btn-sm btn-success"
                disabled={working || (action.kind === "execute_tests" && !tests.length) ||
                    (action.kind === "zeus_investigation" && !runs.length)}
                onclick={() => decide(onConfirm)}
            >
                {#if action.kind === "zeus_investigation"}
                    <Fa icon={faMagnifyingGlass} /> Queue
                {:else if action.kind === "edit_plan"}
                    <Fa icon={faCheck} /> Apply
                {:else}
                    <Fa icon={action.kind === "execute_tests" ? faPlay : faCheck} /> Run
                {/if}
            </button>
            <button type="button" class="btn btn-sm btn-link text-body-secondary text-decoration-none" disabled={working} onclick={() => decide(onDismiss)}>
                <Fa icon={faXmark} /> Dismiss
            </button>
            <span class="text-body-secondary">Anyone can confirm. Nothing runs until then.</span>
        {:else if action.confirmed_by && action.auto}
            <span class="text-body-secondary"
                >Confirmed automatically for {displayName(action.confirmed_by, users)} {ago(action.confirmed_at)}</span
            >
        {:else if action.confirmed_by}
            <span class="text-body-secondary"
                >Confirmed by {displayName(action.confirmed_by, users)} {ago(action.confirmed_at)}</span
            >
        {:else if action.dismissed_by}
            <span class="text-body-secondary">Dismissed by {displayName(action.dismissed_by, users)}</span>
        {/if}
    </div>
</div>
{/if}

<style>
    .badge-spinner {
        width: 0.75em;
        height: 0.75em;
        border-width: 0.15em;
    }
    .run-card:hover {
        background-color: var(--bs-tertiary-bg) !important;
    }
    .action-card.pending {
        border-left: 3px solid var(--bs-warning);
    }
    .params td {
        font-size: 0.75rem;
    }
    .arguments,
    .mcp-result {
        max-height: 16rem;
        overflow: auto;
        white-space: pre-wrap;
        word-break: break-word;
    }
    .zeus-report {
        max-height: 24rem;
        overflow-y: auto;
        font-size: 0.875rem;
    }
</style>
