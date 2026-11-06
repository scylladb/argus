<script lang="ts">
    import Fa from "svelte-fa";
    import { faPen, faPlus, faRotate, faServer, faTrash } from "@fortawesome/free-solid-svg-icons";
    import { fetchJson } from "../Common/ApiUtils";
    import { sendMessage } from "../Stores/AlertStore";
    import { postJson } from "../Chat/chatApi";
    import { ago } from "../Chat/chatFormat";

    const API = "/admin/api/v1/chat/mcp";
    const MODES = [
        { value: "off", label: "Off" },
        { value: "direct", label: "Direct" },
        { value: "confirm", label: "Confirm" },
    ];

    interface McpTool {
        name: string;
        description: string;
        mode: "off" | "direct" | "confirm";
    }

    interface McpServer {
        name: string;
        url: string;
        transport: "streamable_http" | "sse";
        enabled: boolean;
        headers: string[];
        tools: McpTool[];
        probed_at: string | null;
    }

    interface Form {
        name: string;
        url: string;
        transport: "streamable_http" | "sse";
        enabled: boolean;
        headers: { key: string; value: string }[];
        replaceHeaders: boolean;
        editing: boolean;
    }

    let servers = $state<McpServer[] | null>(null);
    let form = $state<Form | null>(null);
    let working = $state<string | null>(null);

    const fail = (error: unknown) =>
        sendMessage("error", error instanceof Error ? error.message : String(error), "ChatMcpManager");

    const load = async () => {
        try {
            servers = await fetchJson<McpServer[]>(API);
        } catch (error) {
            fail(error);
        }
    };

    const replaceServer = (server: McpServer) => {
        servers = (servers ?? []).map((entry) => (entry.name === server.name ? server : entry));
    };

    const save = async () => {
        if (!form) return;
        working = "form";
        try {
            const headers = form.replaceHeaders
                ? Object.fromEntries(form.headers.filter((row) => row.key.trim()).map((row) => [row.key.trim(), row.value]))
                : null;
            await postJson(`${API}/server`, {
                name: form.name.trim(), url: form.url.trim(), transport: form.transport, enabled: form.enabled, headers,
            });
            form = null;
            await load();
        } catch (error) {
            fail(error);
        } finally {
            working = null;
        }
    };

    const probe = async (server: McpServer) => {
        working = server.name;
        try {
            replaceServer(await postJson<McpServer>(`${API}/server/${encodeURIComponent(server.name)}/probe`));
        } catch (error) {
            fail(error);
        } finally {
            working = null;
        }
    };

    const setMode = async (server: McpServer, tool: McpTool, mode: string) => {
        try {
            replaceServer(await postJson<McpServer>(`${API}/server/${encodeURIComponent(server.name)}/tools`,
                                                    { modes: { [tool.name]: mode } }));
        } catch (error) {
            fail(error);
        }
    };

    const toggle = async (server: McpServer) => {
        try {
            await postJson(`${API}/server`, { name: server.name, url: server.url, transport: server.transport,
                                              enabled: !server.enabled, headers: null });
            await load();
        } catch (error) {
            fail(error);
        }
    };

    const remove = async (server: McpServer) => {
        if (!confirm(`Delete the MCP server ${server.name}?`)) return;
        try {
            await postJson(`${API}/server/${encodeURIComponent(server.name)}`, undefined, "DELETE");
            await load();
        } catch (error) {
            fail(error);
        }
    };

    const edit = (server: McpServer | null) => {
        form = server
            ? { name: server.name, url: server.url, transport: server.transport, enabled: server.enabled,
                headers: server.headers.map((key) => ({ key, value: "" })), replaceHeaders: false, editing: true }
            : { name: "", url: "", transport: "streamable_http", enabled: true, headers: [], replaceHeaders: true,
                editing: false };
    };

    load();
</script>

<section class="rounded bg-white shadow-sm p-3">
    <div class="d-flex align-items-center mb-2">
        <h3 class="h6 mb-0">MCP servers</h3>
        <button type="button" class="btn btn-sm btn-outline-primary ms-auto" onclick={() => edit(null)}>
            <Fa icon={faPlus} /> Add server
        </button>
    </div>

    {#if form}
        <form class="rounded bg-light-one p-2 mb-2 d-flex flex-column gap-2 small"
              onsubmit={(event) => { event.preventDefault(); save(); }}>
            <div class="row g-2">
                <div class="col-md-3">
                    <label class="form-label mb-0" for="mcp-name">Name</label>
                    <input id="mcp-name" class="form-control form-control-sm" bind:value={form.name}
                           disabled={form.editing} required pattern="[A-Za-z0-9_\-]+" maxlength="32" />
                </div>
                <div class="col-md-6">
                    <label class="form-label mb-0" for="mcp-url">URL</label>
                    <input id="mcp-url" class="form-control form-control-sm" bind:value={form.url}
                           placeholder="https://host/mcp" required />
                </div>
                <div class="col-md-3">
                    <label class="form-label mb-0" for="mcp-transport">Transport</label>
                    <select id="mcp-transport" class="form-select form-select-sm" bind:value={form.transport}>
                        <option value="streamable_http">Streamable HTTP</option>
                        <option value="sse">SSE</option>
                    </select>
                </div>
            </div>
            <div>
                <div class="d-flex align-items-center gap-2">
                    <span class="form-label mb-0">Headers</span>
                    {#if form.editing && !form.replaceHeaders}
                        <span class="text-body-secondary">{form.headers.map((row) => row.key).join(", ") || "none"}</span>
                        <button type="button" class="btn btn-sm btn-link p-0"
                                onclick={() => form && ((form.replaceHeaders = true), (form.headers = []))}>
                            Replace
                        </button>
                    {:else}
                        <button type="button" class="btn btn-sm btn-link p-0"
                                onclick={() => form?.headers.push({ key: "", value: "" })}>
                            <Fa icon={faPlus} /> Add header
                        </button>
                    {/if}
                </div>
                {#if form.replaceHeaders}
                    {#each form.headers as header, index (index)}
                        <div class="d-flex gap-2 mt-1">
                            <input class="form-control form-control-sm" placeholder="Authorization"
                                   aria-label="Header name" bind:value={header.key} />
                            <input class="form-control form-control-sm" type="password" autocomplete="off"
                                   placeholder="Bearer …" aria-label="Header value" bind:value={header.value} />
                            <button type="button" class="btn btn-sm btn-link text-danger p-0" aria-label="Remove header"
                                    onclick={() => form?.headers.splice(index, 1)}><Fa icon={faTrash} /></button>
                        </div>
                    {/each}
                {/if}
            </div>
            <div class="form-check form-switch mb-0">
                <input id="mcp-enabled" class="form-check-input" type="checkbox" role="switch" bind:checked={form.enabled} />
                <label class="form-check-label" for="mcp-enabled">Enabled</label>
            </div>
            <div class="d-flex gap-2">
                <button type="submit" class="btn btn-sm btn-primary" disabled={working === "form"}>Save</button>
                <button type="button" class="btn btn-sm btn-link text-body-secondary text-decoration-none"
                        onclick={() => (form = null)}>Cancel</button>
            </div>
        </form>
    {/if}

    {#if servers === null}
        <div class="text-body-secondary small"><span class="spinner-border spinner-border-sm"></span> Loading…</div>
    {:else if servers.length === 0}
        <div class="text-body-secondary small">No MCP servers yet.</div>
    {:else}
        <div class="d-flex flex-column gap-2">
            {#each servers as server (server.name)}
                <div class="rounded bg-light-one p-2 small">
                    <div class="d-flex align-items-center gap-2 flex-wrap">
                        <Fa icon={faServer} />
                        <span class="fw-semibold">{server.name}</span>
                        <span class="font-monospace text-body-secondary text-break">{server.url}</span>
                        <span class="badge text-bg-light">{server.transport === "sse" ? "SSE" : "Streamable HTTP"}</span>
                        {#if server.headers.length}
                            <span class="badge text-bg-light" title="Header values are never shown">
                                {server.headers.join(", ")}
                            </span>
                        {/if}
                        <div class="form-check form-switch mb-0 ms-auto" title="Offer this server's tools to the chat">
                            <input id="mcp-on-{server.name}" class="form-check-input" type="checkbox" role="switch"
                                   checked={server.enabled} onchange={() => toggle(server)} />
                            <label class="form-check-label" for="mcp-on-{server.name}">Enabled</label>
                        </div>
                        <button type="button" class="btn btn-sm btn-link p-0" disabled={working === server.name}
                                title="List the server's tools now" onclick={() => probe(server)}>
                            <Fa icon={faRotate} spin={working === server.name} /> Probe
                        </button>
                        <button type="button" class="btn btn-sm btn-link p-0" aria-label="Edit {server.name}"
                                title="Edit the URL, the transport and the headers" onclick={() => edit(server)}>
                            <Fa icon={faPen} />
                        </button>
                        <button type="button" class="btn btn-sm btn-link text-danger p-0" aria-label="Delete {server.name}"
                                title="Delete the server" onclick={() => remove(server)}>
                            <Fa icon={faTrash} />
                        </button>
                    </div>
                    {#if server.tools.length}
                        <table class="table table-sm align-middle mb-0 mt-2 bg-white">
                            <tbody>
                                {#each server.tools as tool (tool.name)}
                                    <tr>
                                        <td class="font-monospace text-nowrap">{tool.name}</td>
                                        <td class="text-body-secondary">{tool.description}</td>
                                        <td class="text-end text-nowrap">
                                            <div class="btn-group btn-group-sm" role="group" aria-label="Mode of {tool.name}">
                                                {#each MODES as mode (mode.value)}
                                                    <button type="button" class="btn"
                                                            class:btn-primary={tool.mode === mode.value}
                                                            class:btn-outline-secondary={tool.mode !== mode.value}
                                                            aria-pressed={tool.mode === mode.value}
                                                            title={mode.value === "direct" ? "Runs when the model calls it"
                                                                : mode.value === "confirm" ? "Proposes a card that a user confirms"
                                                                : "Not offered to the model"}
                                                            onclick={() => setMode(server, tool, mode.value)}>
                                                        {mode.label}
                                                    </button>
                                                {/each}
                                            </div>
                                        </td>
                                    </tr>
                                {/each}
                            </tbody>
                        </table>
                    {:else}
                        <div class="text-body-secondary mt-1">
                            {server.probed_at ? "The server lists no tools." : "Probe the server to list its tools."}
                        </div>
                    {/if}
                    {#if server.probed_at}
                        <div class="text-body-secondary mt-1">Probed {ago(server.probed_at)}</div>
                    {/if}
                </div>
            {/each}
        </div>
    {/if}
</section>
