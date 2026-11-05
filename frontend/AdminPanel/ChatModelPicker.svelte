<script lang="ts">
    import Fa from "svelte-fa";
    import { faCheck, faVial, faXmark } from "@fortawesome/free-solid-svg-icons";
    import ModalWindow from "../Common/ModalWindow.svelte";
    import { fetchJson } from "../Common/ApiUtils";
    import { postJson } from "../Chat/chatApi";
    import type { Connection, DefaultModel, ProbedModel, ToolTestResult } from "../Chat/types";

    const ADMIN_API = "/admin/api/v1/chat";
    const FALLBACK_CONTEXT = 32768;

    interface Props {
        connections: Connection[];
        current: DefaultModel | null;
        onSaved: (model: DefaultModel) => void;
        onClose: () => void;
    }

    let { connections, current, onSaved, onClose }: Props = $props();

    let connection = $state("");
    let models = $state<ProbedModel[] | null>(null);
    let probeError = $state("");
    let filter = $state("");
    let chosen = $state<ProbedModel | null>(null);
    let contextWindow = $state(FALLBACK_CONTEXT);
    let tools = $state(true);
    let vision = $state(false);
    let tests = $state<Record<string, ToolTestResult | "running">>({});
    let saving = $state(false);
    let saveError = $state("");

    const usable = $derived(connections.filter((entry) => entry.token_readable));
    const shown = $derived(
        (models ?? []).filter((model) => model.id.toLowerCase().includes(filter.trim().toLowerCase())),
    );

    const probe = async (name: string) => {
        connection = name;
        models = null;
        chosen = null;
        probeError = "";
        tests = {};
        if (!name) return;
        try {
            models = await fetchJson<ProbedModel[]>(`${ADMIN_API}/connection/${encodeURIComponent(name)}/models`);
            const preselect = models.find((model) => current?.connection === name && model.id === current.model);
            if (preselect) choose(preselect);
        } catch (error) {
            probeError = error instanceof Error ? error.message : String(error);
            models = [];
        }
    };

    const choose = (model: ProbedModel) => {
        chosen = model;
        contextWindow = model.context_window ?? (current?.model === model.id ? current.context_window : FALLBACK_CONTEXT);
        const tested = tests[model.id];
        tools = model.tools ?? (typeof tested === "object" ? tested.tools : true);
        vision = model.vision ?? false;
    };

    const testTools = async (model: ProbedModel) => {
        tests[model.id] = "running";
        try {
            const result = await postJson<ToolTestResult>(
                `${ADMIN_API}/connection/${encodeURIComponent(connection)}/test_tools`, { model: model.id });
            tests[model.id] = result;
            if (chosen?.id === model.id && model.tools === null) tools = result.tools;
        } catch (error) {
            tests[model.id] = { tools: false, detail: error instanceof Error ? error.message : String(error), latency_ms: 0 };
        }
    };

    const save = async () => {
        if (!chosen) return;
        saving = true;
        saveError = "";
        try {
            onSaved(await postJson<DefaultModel>(`${ADMIN_API}/default`, {
                connection, model: chosen.id, context_window: contextWindow, tools, vision,
            }));
        } catch (error) {
            saveError = error instanceof Error ? error.message : String(error);
        } finally {
            saving = false;
        }
    };

    $effect(() => {
        const initial = current?.connection && usable.some((entry) => entry.name === current.connection)
            ? current.connection
            : usable[0]?.name;
        if (initial && !connection) probe(initial);
    });
</script>

{#snippet capability(value: boolean | null, label: string)}
    {#if value === true}
        <span class="badge text-bg-success">{label}</span>
    {:else if value === false}
        <span class="badge text-bg-light text-decoration-line-through">{label}</span>
    {:else}
        <span class="badge text-bg-light" title="The endpoint does not say">{label} ?</span>
    {/if}
{/snippet}

<ModalWindow widthClass="w-75" on:modalClose={onClose}>
    {#snippet title()}Choose the default chat model{/snippet}
    {#snippet body()}
        <div class="d-flex flex-column gap-2">
            <div class="d-flex gap-2 align-items-center flex-wrap">
                <label class="form-label mb-0" for="chat-connection">Connection</label>
                <select id="chat-connection" class="form-select form-select-sm w-auto" value={connection}
                        onchange={(event) => probe((event.currentTarget as HTMLSelectElement).value)}>
                    {#each usable as entry (entry.name)}
                        <option value={entry.name}>{entry.name} ({entry.endpoint})</option>
                    {/each}
                </select>
                <input class="form-control form-control-sm w-auto ms-auto" placeholder="Filter models"
                       aria-label="Filter models" bind:value={filter} />
            </div>

            {#if probeError}
                <div class="alert alert-danger py-1 px-2 small mb-0">Could not list the models: {probeError}</div>
            {:else if models === null}
                <div class="text-body-secondary small"><span class="spinner-border spinner-border-sm"></span> Asking the
                    endpoint for its models…</div>
            {:else}
                <div class="model-table rounded bg-light-one p-1">
                    <table class="table table-sm table-hover mb-0 small align-middle">
                        <thead>
                            <tr><th></th><th>Model</th><th>Context</th><th>Capabilities</th><th>Tool calling</th></tr>
                        </thead>
                        <tbody>
                            {#each shown as model (model.id)}
                                {@const test = tests[model.id]}
                                <tr class:table-active={chosen?.id === model.id} onclick={() => choose(model)}>
                                    <td>
                                        <input type="radio" class="form-check-input" name="chat-model"
                                               aria-label="Choose {model.id}" checked={chosen?.id === model.id}
                                               onchange={() => choose(model)} />
                                    </td>
                                    <td class="font-monospace text-break">{model.id}</td>
                                    <td>{model.context_window?.toLocaleString() ?? "?"}</td>
                                    <td class="d-flex gap-1">
                                        {@render capability(model.tools, "tool-calling")}
                                        {@render capability(model.vision, "vision")}
                                    </td>
                                    <td>
                                        {#if test === "running"}
                                            <span class="spinner-border spinner-border-sm"></span>
                                        {:else if test}
                                            <span class:text-success={test.tools} class:text-danger={!test.tools} title={test.detail}>
                                                <Fa icon={test.tools ? faCheck : faXmark} />
                                                {test.tools ? "works" : "no"} · {test.latency_ms} ms
                                            </span>
                                        {:else}
                                            <button type="button" class="btn btn-sm btn-outline-secondary py-0"
                                                    onclick={(event) => { event.stopPropagation(); testTools(model); }}>
                                                <Fa icon={faVial} /> Test
                                            </button>
                                        {/if}
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            {/if}

            {#if chosen}
                <div class="rounded bg-light-one p-2 d-flex gap-3 align-items-end flex-wrap small">
                    <div>
                        <label class="form-label mb-0" for="chat-context">Context window (tokens)</label>
                        <input id="chat-context" type="number" min="1" class="form-control form-control-sm"
                               bind:value={contextWindow} />
                    </div>
                    <div class="form-check">
                        <input id="chat-tools" type="checkbox" class="form-check-input" bind:checked={tools} />
                        <label class="form-check-label" for="chat-tools">Send tools</label>
                    </div>
                    <div class="form-check">
                        <input id="chat-vision" type="checkbox" class="form-check-input" bind:checked={vision} />
                        <label class="form-check-label" for="chat-vision">Vision</label>
                    </div>
                    <button type="button" class="btn btn-sm btn-primary ms-auto" disabled={saving || contextWindow < 1}
                            onclick={save}>Set {chosen.id} as default</button>
                </div>
                {#if !tools}
                    <div class="alert alert-warning py-1 px-2 small mb-0">
                        Without tool calling the chat answers from the summary and the memories only. It cannot look
                        up runs, start tests, or write memories.
                    </div>
                {/if}
            {/if}
            {#if saveError}<div class="alert alert-danger py-1 px-2 small mb-0">{saveError}</div>{/if}
        </div>
    {/snippet}
</ModalWindow>

<style>
    .model-table {
        max-height: 50vh;
        overflow-y: auto;
    }
    tbody tr {
        cursor: pointer;
    }
</style>
