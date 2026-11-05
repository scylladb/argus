<script lang="ts">
    import Fa from "svelte-fa";
    import { faIdBadge, faPen, faPlug, faPlus, faTrash } from "@fortawesome/free-solid-svg-icons";
    import { fetchJson } from "../Common/ApiUtils";
    import ModalWindow from "../Common/ModalWindow.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { postJson } from "../Chat/chatApi";
    import { ago } from "../Chat/chatFormat";
    import AssistantAvatar from "../Chat/AssistantAvatar.svelte";
    import type { AssistantIdentity, Connection, DefaultModel } from "../Chat/types";
    import ChatIdentityEditor from "./ChatIdentityEditor.svelte";
    import ChatMcpManager from "./ChatMcpManager.svelte";
    import ChatPromptManager from "./ChatPromptManager.svelte";
    import ChatModelPicker from "./ChatModelPicker.svelte";

    const ADMIN_API = "/admin/api/v1/chat";
    const TABS = [
        { id: "models", label: "Models" },
        { id: "mcp", label: "MCP servers" },
        { id: "prompt", label: "Prompt & skills" },
    ] as const;

    let tab = $state<(typeof TABS)[number]["id"]>("models");

    interface Form {
        name: string;
        endpoint: string;
        token: string;
        editing: boolean;
    }

    let connections = $state<Connection[] | null>(null);
    let defaultModel = $state<DefaultModel | null>(null);
    let form = $state<Form | null>(null);
    let deleting = $state<Connection | null>(null);
    let picking = $state(false);
    let identities = $state<AssistantIdentity[]>([]);
    let activeIdentity = $state<string | null>(null);
    let editingIdentity = $state<string | null>(null);

    const identityOf = (connection: string) => identities.find((identity) => identity.connection === connection) ?? null;
    let working = $state(false);

    const fail = (error: unknown) =>
        sendMessage("error", error instanceof Error ? error.message : String(error), "ChatConfigManager");

    const load = async () => {
        try {
            const response = await fetchJson<{
                connections: Connection[];
                default: DefaultModel | null;
                identities: AssistantIdentity[];
                active_identity: string | null;
            }>(`${ADMIN_API}/connections`);
            connections = response.connections;
            defaultModel = response.default;
            identities = response.identities ?? [];
            activeIdentity = response.active_identity ?? null;
        } catch (error) {
            fail(error);
        }
    };

    const save = async () => {
        if (!form) return;
        working = true;
        try {
            await postJson(`${ADMIN_API}/connection`, {
                name: form.name.trim(), endpoint: form.endpoint.trim(), token: form.token || null,
            });
            form = null;
            await load();
        } catch (error) {
            fail(error);
        } finally {
            working = false;
        }
    };

    const setActive = async (connection: string | null) => {
        working = true;
        try {
            await postJson(`${ADMIN_API}/identity/active`, { connection });
            activeIdentity = connection;
        } catch (error) {
            fail(error);
        } finally {
            working = false;
        }
    };

    const remove = async (connection: Connection) => {
        working = true;
        try {
            await postJson(`${ADMIN_API}/connection/${encodeURIComponent(connection.name)}`, undefined, "DELETE");
            deleting = null;
            await load();
        } catch (error) {
            fail(error);
        } finally {
            working = false;
        }
    };

    load();
</script>

<div class="p-3 d-flex flex-column gap-3">
    <div>
        <h2 class="h4">Chat</h2>
        <p class="text-body-secondary mb-0">
            Models, tools and instructions for the release and view chat.
        </p>
    </div>

    <ul class="nav nav-underline" role="tablist">
        {#each TABS as entry (entry.id)}
            <li class="nav-item">
                <button type="button" class="nav-link" class:active={tab === entry.id} role="tab"
                        aria-selected={tab === entry.id} onclick={() => (tab = entry.id)}>{entry.label}</button>
            </li>
        {/each}
    </ul>

    {#if tab === "models"}
    <section class="rounded bg-white shadow-sm p-3">
        <div class="d-flex align-items-center mb-2">
            <h3 class="h6 mb-0">Default model</h3>
            <button type="button" class="btn btn-sm btn-primary ms-auto" disabled={!connections?.length}
                    onclick={() => (picking = true)}>Change default model</button>
        </div>
        <div class="rounded bg-light-one p-2 small">
            {#if defaultModel}
                <div class="fw-semibold font-monospace">{defaultModel.model}</div>
                <div class="text-body-secondary">
                    on {defaultModel.connection} · {defaultModel.context_window.toLocaleString()} tokens
                    · {defaultModel.tools ? "tools" : "no tools"}{defaultModel.vision ? " · vision" : ""}
                    {#if defaultModel.set_at}· set {ago(defaultModel.set_at)}{/if}
                </div>
            {:else}
                <span class="text-body-secondary">No default is set. The chat uses the first argus_web.yaml connection
                    that names a model, if any.</span>
            {/if}
        </div>
    </section>

    <section class="rounded bg-white shadow-sm p-3">
        <div class="d-flex align-items-center mb-2">
            <h3 class="h6 mb-0">Connections</h3>
            <button type="button" class="btn btn-sm btn-outline-primary ms-auto"
                    onclick={() => (form = { name: "", endpoint: "", token: "", editing: false })}>
                <Fa icon={faPlus} /> Add connection
            </button>
        </div>
        {#if connections === null}
            <div class="text-body-secondary small"><span class="spinner-border spinner-border-sm"></span> Loading…</div>
        {:else if connections.length === 0}
            <div class="text-body-secondary small">No connections yet.</div>
        {:else}
            <div class="d-flex flex-column gap-2">
                {#each connections as connection (connection.name)}
                    {@const identity = identityOf(connection.name)}
                    <div class="rounded bg-light-one p-2 d-flex align-items-center gap-2 small flex-wrap">
                        <Fa icon={faPlug} />
                        <span class="fw-semibold">{connection.name}</span>
                        <span class="font-monospace text-body-secondary text-break">{connection.endpoint}</span>
                        <span class="badge {connection.source === 'config' ? 'text-bg-secondary' : 'text-bg-info'}">
                            {connection.source === "config" ? "argus_web.yaml" : "Admin Panel"}
                        </span>
                        {#if !connection.token_readable}
                            <span class="badge text-bg-danger">Token unreadable: enter it again</span>
                        {:else if connection.token_set}
                            <span class="badge text-bg-light">Token set</span>
                        {:else}
                            <span class="badge text-bg-light">No token</span>
                        {/if}
                        {#if identity}
                            <span class="d-inline-flex align-items-center gap-1" title="Assistant identity">
                                <AssistantAvatar assistant={identity} size={20} /> {identity.name}
                            </span>
                            {#if activeIdentity === connection.name}
                                <span class="badge text-bg-success">Active identity</span>
                                <button type="button" class="btn btn-sm btn-link text-body-secondary text-decoration-none p-0"
                                        disabled={working} onclick={() => setActive(null)}>Stop using</button>
                            {:else}
                                <button type="button" class="btn btn-sm btn-link text-decoration-none p-0"
                                        disabled={working} onclick={() => setActive(connection.name)}>Use this identity</button>
                            {/if}
                        {/if}
                        <button type="button" class="btn btn-sm btn-link ms-auto p-0" aria-label="Identity of {connection.name}"
                                title="Assistant name and picture" onclick={() => (editingIdentity = connection.name)}>
                            <Fa icon={faIdBadge} />
                        </button>
                        {#if connection.source === "database"}
                            <button type="button" class="btn btn-sm btn-link p-0" aria-label="Edit {connection.name}"
                                    title="Edit the endpoint and the token"
                                    onclick={() => (form = { name: connection.name, endpoint: connection.endpoint, token: "",
                                                             editing: true })}>
                                <Fa icon={faPen} />
                            </button>
                            <button type="button" class="btn btn-sm btn-link text-danger p-0"
                                    aria-label="Delete {connection.name}" title="Delete the connection" onclick={() => (deleting = connection)}>
                                <Fa icon={faTrash} />
                            </button>
                        {/if}
                    </div>
                {/each}
            </div>
        {/if}

        {#if form}
            <form class="rounded bg-light-one p-2 mt-2 d-flex flex-column gap-2 small"
                  onsubmit={(event) => { event.preventDefault(); save(); }}>
                <div class="row g-2">
                    <div class="col-md-3">
                        <label class="form-label mb-0" for="chat-name">Name</label>
                        <input id="chat-name" class="form-control form-control-sm" bind:value={form.name}
                               disabled={form.editing} required pattern="[A-Za-z0-9._\-]+" />
                    </div>
                    <div class="col-md-5">
                        <label class="form-label mb-0" for="chat-endpoint">Endpoint</label>
                        <input id="chat-endpoint" class="form-control form-control-sm" bind:value={form.endpoint}
                               placeholder="https://host/api" required />
                    </div>
                    <div class="col-md-4">
                        <label class="form-label mb-0" for="chat-token">Token</label>
                        <input id="chat-token" type="password" autocomplete="off" class="form-control form-control-sm"
                               bind:value={form.token}
                               placeholder={form.editing ? "Leave empty to keep the stored token" : "sk-…"} />
                    </div>
                </div>
                <div class="d-flex gap-2">
                    <button type="submit" class="btn btn-sm btn-primary" disabled={working}>Save</button>
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick={() => (form = null)}>Cancel</button>
                </div>
            </form>
        {/if}
    </section>
    {:else if tab === "mcp"}
        <ChatMcpManager />
    {:else}
        <ChatPromptManager />
    {/if}
</div>

{#if picking && connections}
    <ChatModelPicker
        {connections}
        current={defaultModel}
        onSaved={(model) => {
            defaultModel = model;
            picking = false;
            sendMessage("success", `${model.model} answers in every chat now.`, "ChatConfigManager");
        }}
        onClose={() => (picking = false)}
    />
{/if}

{#if editingIdentity}
    <ChatIdentityEditor
        connection={editingIdentity}
        identity={identityOf(editingIdentity)}
        onSaved={() => {
            editingIdentity = null;
            load();
        }}
        onClose={() => (editingIdentity = null)}
    />
{/if}

{#if deleting}
    <ModalWindow on:modalClose={() => (deleting = null)}>
        {#snippet title()}Delete the connection {deleting?.name}{/snippet}
        {#snippet body()}
            <p>
                {defaultModel?.connection === deleting?.name
                    ? "This connection carries the default model. Without a default, chats stop answering until you pick another."
                    : "Chats do not use this connection."}
            </p>
            <div class="d-flex gap-2 justify-content-end">
                <button type="button" class="btn btn-outline-secondary" onclick={() => (deleting = null)}>Cancel</button>
                <button type="button" class="btn btn-danger" disabled={working}
                        onclick={() => deleting && remove(deleting)}>Delete</button>
            </div>
        {/snippet}
    </ModalWindow>
{/if}
