<script lang="ts">
    import Fa from "svelte-fa";
    import {
        faLightbulb,
        faNoteSticky,
        faPen,
        faPlus,
        faRobot,
        faRotateLeft,
        faTrash,
    } from "@fortawesome/free-solid-svg-icons";
    import type { User } from "../Common/UserTypes";
    import { sendMessage } from "../Stores/AlertStore";
    import { fetchJson } from "../Common/ApiUtils";
    import { autosize } from "./autosize";
    import { postJson } from "./chatApi";
    import { ago, displayName } from "./chatFormat";
    import type { Memory, MemoryScope, Revision } from "./types";

    interface Props {
        base: string;
        tab: "list" | "history";
        memories: Memory[];
        scopes: MemoryScope[];
        users: Record<string, User>;
        onChange: (memories: Memory[]) => void;
    }

    let { base, tab, memories, scopes, users, onChange }: Props = $props();

    type Kind = Memory["kind"];

    let draft = $state("");
    let draftFinding = $state(false);
    let draftScope = $state("");
    let editing = $state<string | null>(null);
    let editText = $state("");
    let editFinding = $state(false);
    let history = $state<Revision[] | null>(null);
    let working = $state(false);

    const ownScope = $derived(scopes[0]);
    const targetScope = $derived(draftScope || ownScope?.id || "");
    const kindOf = (finding: boolean): Kind => (finding ? "finding" : "note");

    const scopeLabel = (scope: MemoryScope) =>
        scope.id === ownScope?.id ? `This ${scope.type}` : `${scope.type === "release" ? "Release" : "View"} ${scope.name}`;

    const fail = (error: unknown) =>
        sendMessage("error", error instanceof Error ? error.message : String(error), "ChatMemories");

    const loadHistory = async () => {
        try {
            history = await fetchJson<Revision[]>(`${base}/memories/history`);
        } catch (error) {
            fail(error);
        }
    };

    const refresh = async () => {
        onChange(await fetchJson<Memory[]>(`${base}/memories`));
        if (tab === "history") await loadHistory();
    };

    const run = async (work: () => Promise<unknown>) => {
        working = true;
        try {
            await work();
            await refresh();
        } catch (error) {
            fail(error);
        } finally {
            working = false;
        }
    };

    const add = () =>
        run(async () => {
            await postJson(`${base}/memories`, {
                content: draft,
                kind: kindOf(draftFinding),
                scope: targetScope && targetScope !== ownScope?.id ? targetScope : null,
            });
            draft = "";
            draftFinding = false;
        });

    const startEdit = (memory: Memory) => {
        editing = memory.id;
        editText = memory.content;
        editFinding = memory.kind === "finding";
    };

    const saveEdit = (memory: Memory) =>
        run(async () => {
            await postJson(`${base}/memories/${memory.id}`, { content: editText, kind: kindOf(editFinding) }, "PUT");
            editing = null;
        });

    const remove = (memory: Memory) => run(() => postJson(`${base}/memories/${memory.id}`, undefined, "DELETE"));

    const revert = (revision: Revision) => run(() => postJson(`${base}/memories/history/${revision.revision}/revert`));

    const actionLabel: Record<Revision["action"], string> = {
        create: "added",
        update: "changed",
        delete: "deleted",
        revert: "reverted",
    };

    $effect(() => {
        if (tab === "history") loadHistory();
    });
</script>

{#snippet kindPill(kind: string)}
    <span class="kind-pill badge rounded-pill {kind === 'finding' ? 'text-bg-warning' : 'text-bg-secondary'}">
        <Fa icon={kind === "finding" ? faLightbulb : faNoteSticky} />
        {kind === "finding" ? "Finding" : "Note"}
    </span>
{/snippet}

{#if tab === "list"}
    <form class="card-block rounded bg-white shadow-sm p-2 d-flex flex-column gap-2"
          onsubmit={(event) => { event.preventDefault(); add(); }}>
        <textarea class="form-control form-control-sm bg-light-one border-0" rows="2" bind:value={draft}
                  use:autosize={draft} aria-label="New memory"
                  placeholder={draftFinding ? "Create finding" : "Create memory"}></textarea>
        <div class="form-check form-switch small mb-0">
            <input id="memory-finding" class="form-check-input" type="checkbox" role="switch" bind:checked={draftFinding} />
            <label class="form-check-label" for="memory-finding">Finding: shows in the release summary</label>
        </div>
        <div class="d-flex gap-2 align-items-center">
            {#if scopes.length > 1}
                <label class="small text-body-secondary text-nowrap" for="memory-scope">Store on</label>
                <select id="memory-scope" class="form-select form-select-sm" value={targetScope}
                        onchange={(event) => (draftScope = (event.currentTarget as HTMLSelectElement).value)}>
                    {#each scopes as scope (scope.id)}
                        <option value={scope.id}>{scopeLabel(scope)}</option>
                    {/each}
                </select>
            {/if}
            <button type="submit" class="btn btn-sm btn-primary ms-auto text-nowrap" disabled={working || !draft.trim()}>
                <Fa icon={faPlus} /> Add
            </button>
        </div>
    </form>

    {#if memories.length === 0}
        <div class="small text-body-secondary px-1">
            No memories yet.
        </div>
    {/if}
    {#each memories as memory (memory.id)}
        <article class="card-block rounded bg-white shadow-sm p-2 small" class:finding={memory.kind === "finding"}>
            {#if editing === memory.id}
                <textarea class="form-control form-control-sm bg-light-one border-0 mb-2" rows="3" bind:value={editText}
                          use:autosize={editText} aria-label="Memory text"></textarea>
                <div class="d-flex align-items-center gap-2">
                    <div class="form-check form-switch mb-0">
                        <input id="edit-finding-{memory.id}" class="form-check-input" type="checkbox" role="switch"
                               bind:checked={editFinding} />
                        <label class="form-check-label" for="edit-finding-{memory.id}">Finding</label>
                    </div>
                    <button type="button" class="btn btn-sm btn-link text-body-secondary text-decoration-none ms-auto"
                            onclick={() => (editing = null)}>Cancel</button>
                    <button type="button" class="btn btn-sm btn-primary" disabled={working}
                            onclick={() => saveEdit(memory)}>Save</button>
                </div>
            {:else}
                <header class="d-flex align-items-center gap-2 mb-1">
                    {@render kindPill(memory.kind)}
                    {#if memory.entity_id !== ownScope?.id}
                        <span class="text-body-secondary text-truncate" title={memory.entity_name}>
                            {memory.entity_type} {memory.entity_name}
                        </span>
                    {/if}
                    <span class="ms-auto d-inline-flex gap-2">
                        <button type="button" class="btn btn-sm btn-link text-body-secondary p-0" aria-label="Edit memory"
                                onclick={() => startEdit(memory)}><Fa icon={faPen} /></button>
                        <button type="button" class="btn btn-sm btn-link text-body-secondary p-0" aria-label="Delete memory"
                                disabled={working} onclick={() => remove(memory)}><Fa icon={faTrash} /></button>
                    </span>
                </header>
                <div class="memory-text">{memory.content}</div>
                <footer class="text-body-secondary mt-1">
                    {displayName(memory.updated_by, users)} · {ago(memory.updated_at)}
                    {#if memory.source_node}<span title="Written from the chat"><Fa icon={faRobot} /></span>{/if}
                </footer>
            {/if}
        </article>
    {/each}
{:else if history === null}
    <div class="small text-body-secondary px-1"><span class="spinner-border spinner-border-sm"></span> Loading the history…</div>
{:else if history.length === 0}
    <div class="small text-body-secondary px-1">No changes yet.</div>
{:else}
    {#each history as revision (revision.revision)}
        <article class="card-block rounded bg-white shadow-sm p-2 small">
            <header class="d-flex align-items-center gap-2 mb-1">
                {@render kindPill(revision.kind)}
                <span><span class="fw-semibold">{displayName(revision.user_id, users)}</span> {actionLabel[revision.action]}</span>
                {#if revision.source === "chat"}<span title="From the chat"><Fa icon={faRobot} /></span>{/if}
                <span class="text-body-secondary ms-auto text-nowrap">{ago(revision.created_at)}</span>
            </header>
            {#if revision.before !== null}<div class="diff before rounded px-2 py-1 mb-1">{revision.before}</div>{/if}
            {#if revision.after !== null}<div class="diff after rounded px-2 py-1">{revision.after}</div>{/if}
            <div class="d-flex mt-1">
                <button type="button" class="btn btn-sm btn-link text-decoration-none p-0 ms-auto" disabled={working}
                        onclick={() => revert(revision)}>
                    <Fa icon={faRotateLeft} /> Revert this change
                </button>
            </div>
        </article>
    {/each}
{/if}

<style>
    .card-block.finding {
        border-left: 3px solid var(--bs-warning);
    }
    .kind-pill {
        font-weight: 500;
    }
    .memory-text,
    .diff {
        white-space: pre-wrap;
        overflow-wrap: anywhere;
    }
    .diff.before {
        text-decoration: line-through;
        background-color: var(--bs-danger-bg-subtle);
        color: var(--bs-danger-text-emphasis);
    }
    .diff.after {
        background-color: var(--bs-success-bg-subtle);
        color: var(--bs-success-text-emphasis);
    }
    textarea {
        resize: none;
        max-height: 14rem;
    }
</style>
