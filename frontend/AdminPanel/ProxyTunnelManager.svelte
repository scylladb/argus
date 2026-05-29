<script lang="ts">
    import Fa from "svelte-fa";
    import { faTimes, faCopy } from "@fortawesome/free-solid-svg-icons";
    import queryString from "query-string";
    import ModalWindow from "../Common/ModalWindow.svelte";
    import { timestampToISODate } from "../Common/DateUtils";
    import { fetchJson } from "../Common/ApiUtils";
    import { sendMessage } from "../Stores/AlertStore";
    import ProxyTunnelCreateForm from "./ProxyTunnelCreateForm.svelte";

    const ADMIN_API = "/admin/api/v1";

    interface TunnelConfig {
        id: string;
        host: string;
        port: number;
        proxy_user: string;
        target_host: string;
        target_port: number;
        is_active: boolean;
        host_key_fingerprint?: string;
        service_user_id?: string;
        api_token?: string;
    }

    interface SshKey {
        key_id: string;
        fingerprint: string;
        tunnel_id: string;
        user_id: string;
        created_at: string;
        expires_at: string;
    }

    interface CreateForm {
        host: string;
        port: number;
        proxy_user: string;
        target_host: string;
        target_port: number;
        is_active: boolean;
    }

    let working = $state(false);

    let showCreateForm = $state(false);
    let createdConfig = $state<TunnelConfig | null>(null);

    let confirmDeleteKey = $state(false);
    let selectedKey = $state<SshKey | null>(null);

    let confirmToggleActive = $state(false);
    let toggleTarget = $state<TunnelConfig | null>(null);

    let confirmDeleteConfig = $state(false);
    let deleteTarget = $state<TunnelConfig | null>(null);
    let deleteServiceUser = $state(false);

    let activeFilter = $state("all");

    const loadConfigs = async (): Promise<TunnelConfig[]> => {
        const params: Record<string, string> = {};
        if (activeFilter === "active") params.active_only = "true";
        if (activeFilter === "inactive") params.active_only = "false";
        const qs = queryString.stringify(params);
        return await fetchJson<TunnelConfig[]>(`${ADMIN_API}/proxy-tunnel/configs${qs ? `?${qs}` : ""}`);
    };

    const loadKeys = async (): Promise<SshKey[]> => await fetchJson<SshKey[]>(`${ADMIN_API}/ssh/keys`);

    let configsPromise = $state(loadConfigs());
    let keysPromise = $state(loadKeys());

    const refreshConfigs = () => {
        configsPromise = loadConfigs();
    };
    const refreshKeys = () => {
        keysPromise = loadKeys();
    };

    const copy = (value: string) => navigator.clipboard.writeText(value);

    const knownHost = (entry: string | null | undefined): { type: string; key: string } => {
        if (!entry) return { type: "—", key: "—" };
        const parts = entry.trim().split(/\s+/);
        if (parts.length < 3) return { type: "?", key: entry };
        return { type: parts[1], key: parts[2] };
    };

    const submitCreate = async (form: CreateForm) => {
        try {
            working = true;
            const config = await fetchJson<TunnelConfig>(`${ADMIN_API}/proxy-tunnel/config`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(form),
            });
            showCreateForm = false;
            createdConfig = config;
            refreshConfigs();
        } catch (error: any) {
            console.error("ProxyTunnelManager::submitCreate", error);
            sendMessage("error", error.message, "ProxyTunnelManager::submitCreate");
        } finally {
            working = false;
        }
    };

    const submitToggleActive = async () => {
        if (!toggleTarget) return;
        try {
            working = true;
            await fetchJson(`${ADMIN_API}/proxy-tunnel/config/${toggleTarget.id}/active`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ is_active: !toggleTarget.is_active }),
            });
            refreshConfigs();
        } catch (error: any) {
            console.error("ProxyTunnelManager::submitToggleActive", error);
            sendMessage("error", error.message, "ProxyTunnelManager::submitToggleActive");
        } finally {
            working = false;
            confirmToggleActive = false;
            toggleTarget = null;
        }
    };

    const submitDeleteConfig = async () => {
        if (!deleteTarget) return;
        try {
            working = true;
            await fetchJson(`${ADMIN_API}/proxy-tunnel/config/${deleteTarget.id}`, {
                method: "DELETE",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ delete_user: deleteServiceUser }),
            });
            refreshConfigs();
            refreshKeys();
        } catch (error: any) {
            console.error("ProxyTunnelManager::submitDeleteConfig", error);
            sendMessage("error", error.message, "ProxyTunnelManager::submitDeleteConfig");
        } finally {
            working = false;
            confirmDeleteConfig = false;
            deleteTarget = null;
            deleteServiceUser = false;
        }
    };

    const submitDeleteKey = async () => {
        if (!selectedKey) return;
        try {
            working = true;
            await fetchJson(`${ADMIN_API}/ssh/keys/${selectedKey.key_id}`, { method: "DELETE" });
            refreshKeys();
        } catch (error: any) {
            console.error("ProxyTunnelManager::submitDeleteKey", error);
            sendMessage("error", error.message, "ProxyTunnelManager::submitDeleteKey");
        } finally {
            working = false;
            confirmDeleteKey = false;
            selectedKey = null;
        }
    };

</script>

{#snippet copyCell(value: string)}
    <span class="text-truncate" title={value}>{value}</span>
    <button
        class="btn btn-link btn-sm p-0 ms-1 align-baseline"
        title="Copy to clipboard"
        aria-label="Copy to clipboard"
        onclick={() => copy(value)}
    >
        <Fa icon={faCopy} />
    </button>
{/snippet}

{#if showCreateForm}
    <ProxyTunnelCreateForm {working} onsubmit={submitCreate} oncancel={() => (showCreateForm = false)} />
{/if}

{#if confirmToggleActive && toggleTarget}
    <ModalWindow on:modalClose={() => (confirmToggleActive = false)}>
        {#snippet title()}<div>{toggleTarget.is_active ? "Disable" : "Enable"} proxy tunnel</div>{/snippet}
        {#snippet body()}
            <div>
                <div>
                    {#if toggleTarget.is_active}
                        Disable <span class="fw-bold">{toggleTarget.host}:{toggleTarget.port}</span>?
                        Established client tunnels keep working until reconnect.
                    {:else}
                        Re-enable <span class="fw-bold">{toggleTarget.host}:{toggleTarget.port}</span>?
                        New tunnel registrations may be routed to this host.
                    {/if}
                </div>
                <div class="d-flex align-items-center my-3">
                    <button class="btn btn-warning w-75 me-2" disabled={working} onclick={submitToggleActive}>Confirm</button>
                    <button class="btn btn-secondary w-25" disabled={working} onclick={() => (confirmToggleActive = false)}>Cancel</button>
                </div>
            </div>
        {/snippet}
    </ModalWindow>
{/if}

{#if confirmDeleteConfig && deleteTarget}
    <ModalWindow on:modalClose={() => { confirmDeleteConfig = false; deleteServiceUser = false; }}>
        {#snippet title()}<div>Delete proxy tunnel</div>{/snippet}
        {#snippet body()}
            <div>
                <div>
                    Permanently delete <span class="fw-bold">{deleteTarget.host}:{deleteTarget.port}</span>?
                </div>
                <div class="text-muted small mt-2">
                    The associated API token is invalidated. The proxy host will refuse new connections after its <code>argus-cli</code> token stops working.
                </div>
                <div class="form-check form-switch mt-3">
                    <input
                        id="deleteServiceUser"
                        class="form-check-input"
                        type="checkbox"
                        role="switch"
                        bind:checked={deleteServiceUser}
                    />
                    <label class="form-check-label" for="deleteServiceUser">
                        Also delete the service user
                    </label>
                </div>
                {#if deleteServiceUser}
                    <div class="alert alert-warning py-2 mt-2 small mb-0">
                        The service user <code>{deleteTarget.proxy_user}</code> will be permanently removed.
                    </div>
                {/if}
                <div class="d-flex align-items-center my-3">
                    <button class="btn btn-danger w-75 me-2" disabled={working} onclick={submitDeleteConfig}>Delete</button>
                    <button class="btn btn-secondary w-25" disabled={working} onclick={() => { confirmDeleteConfig = false; deleteServiceUser = false; }}>Cancel</button>
                </div>
            </div>
        {/snippet}
    </ModalWindow>
{/if}

{#if confirmDeleteKey && selectedKey}
    <ModalWindow on:modalClose={() => (confirmDeleteKey = false)}>
        {#snippet title()}<div>Revoke SSH key</div>{/snippet}
        {#snippet body()}
            <div>
                <div>
                    Revoke key <span class="font-monospace text-break">{selectedKey.fingerprint}</span>?
                </div>
                <div class="text-muted small mt-2">
                    Effective on next SSH connection — does not kill an established tunnel.
                </div>
                <div class="d-flex align-items-center my-3">
                    <button class="btn btn-danger w-75 me-2" disabled={working} onclick={submitDeleteKey}>Revoke</button>
                    <button class="btn btn-secondary w-25" disabled={working} onclick={() => (confirmDeleteKey = false)}>Cancel</button>
                </div>
            </div>
        {/snippet}
    </ModalWindow>
{/if}

<div class="p-2">
    {#if createdConfig?.api_token}
        <div class="alert alert-info">
            <div class="fw-bold mb-1">Service user API token (shown once)</div>
            <div class="d-flex align-items-center">
                <code class="text-break flex-grow-1">{createdConfig.api_token}</code>
                <button
                    class="btn btn-sm btn-outline-primary ms-2"
                    onclick={() => copy(createdConfig!.api_token!)}
                >
                    <Fa icon={faCopy} /> Copy
                </button>
                <button class="btn btn-sm ms-2" aria-label="Dismiss token" onclick={() => (createdConfig = null)}>
                    <Fa icon={faTimes} />
                </button>
            </div>
            <div class="small mt-1">
                Embed this token in the proxy host's <code>argus-authorized-keys</code> wrapper
                (see <code>scripts/tunnel-server-setup.sh</code>).
            </div>
        </div>
    {/if}

    <!-- Proxy Tunnels -->
    <div class="bg-white rounded mb-3">
        <div class="d-flex align-items-center p-2 border-bottom">
            <h5 class="m-0">Proxy Tunnels</h5>
            <div class="ms-auto d-flex align-items-center">
                <select class="form-select form-select-sm me-2" bind:value={activeFilter} onchange={refreshConfigs}>
                    <option value="all">All</option>
                    <option value="active">Active only</option>
                    <option value="inactive">Inactive only</option>
                </select>
                <button class="btn btn-sm btn-outline-secondary me-2" onclick={refreshConfigs}>Refresh</button>
                <button
                    class="btn btn-sm btn-primary"
                    onclick={() => (showCreateForm = true)}
                >
                    Add Proxy
                </button>
            </div>
        </div>

        {#await configsPromise}
            <div class="p-3 text-center text-muted">
                <span class="spinner-border spinner-border-sm"></span> Loading proxy tunnels...
            </div>
        {:then configs}
            {#if !configs || configs.length === 0}
                <div class="p-3 text-center text-muted">No proxy tunnel configs.</div>
            {:else}
                {#each configs as config (config.id)}
                    {@const kh = knownHost(config.host_key_fingerprint)}
                    <div class="px-3 py-2 border-bottom">
                        <div class="d-flex flex-wrap align-items-center">
                            <span class="font-monospace fw-semibold">{config.host}:{config.port}</span>
                            <button
                                class="btn btn-link btn-sm p-0 ms-1 align-baseline"
                                title="Copy host"
                                aria-label="Copy host"
                                onclick={() => copy(`${config.host}:${config.port}`)}
                            >
                                <Fa icon={faCopy} />
                            </button>
                            <span class="badge bg-light text-dark border ms-2 font-monospace fw-normal">
                                → {config.target_host}:{config.target_port}
                            </span>
                            <div class="ms-auto d-flex align-items-center">
                                {#if config.is_active}
                                    <span class="badge bg-success me-2">Active</span>
                                {:else}
                                    <span class="badge bg-secondary me-2">Inactive</span>
                                {/if}
                                <div class="btn-group btn-group-sm">
                                    <button
                                        class="btn {config.is_active ? 'btn-outline-warning' : 'btn-outline-success'}"
                                        disabled={working}
                                        onclick={() => {
                                            toggleTarget = config;
                                            confirmToggleActive = true;
                                        }}
                                    >
                                        {config.is_active ? "Disable" : "Enable"}
                                    </button>
                                    <button
                                        class="btn btn-outline-danger"
                                        disabled={working}
                                        onclick={() => {
                                            deleteTarget = config;
                                            confirmDeleteConfig = true;
                                        }}
                                    >
                                        Delete
                                    </button>
                                </div>
                            </div>
                        </div>
                        <div class="d-flex flex-wrap align-items-center mt-1 small text-muted">
                            <span class="me-1">Proxy user:</span>
                            <span class="font-monospace text-dark me-1">{config.proxy_user}</span>
                            <button
                                class="btn btn-link btn-sm p-0 me-3 align-baseline"
                                title="Copy proxy user"
                                aria-label="Copy proxy user"
                                onclick={() => copy(config.proxy_user)}
                            >
                                <Fa icon={faCopy} />
                            </button>
                            <span class="me-1">Service user:</span>
                            {#if config.service_user_id}
                                {@const svcUser = config.service_user_id}
                                <span class="font-monospace text-dark me-1">{svcUser}</span>
                                <button
                                    class="btn btn-link btn-sm p-0 me-3 align-baseline"
                                    title="Copy service user"
                                    aria-label="Copy service user"
                                    onclick={() => copy(svcUser)}
                                >
                                    <Fa icon={faCopy} />
                                </button>
                            {:else}
                                <span class="me-3">—</span>
                            {/if}
                            <span class="me-1">Host key:</span>
                            <span class="badge bg-light text-dark border me-1">{kh.type}</span>
                            <span class="font-monospace text-dark text-truncate me-1 host-key-fp" title={config.host_key_fingerprint}>
                                {kh.key}
                            </span>
                            <button
                                class="btn btn-link btn-sm p-0 align-baseline"
                                title="Copy known_hosts entry"
                                aria-label="Copy known_hosts entry"
                                onclick={() => copy(config.host_key_fingerprint ?? "")}
                            >
                                <Fa icon={faCopy} />
                            </button>
                        </div>
                    </div>
                {/each}
            {/if}
        {:catch error}
            <div class="alert alert-danger m-2">{error.message}</div>
        {/await}
    </div>

    <!-- Registered SSH Keys -->
    <div class="bg-white rounded">
        <div class="d-flex align-items-center p-2 border-bottom">
            <h5 class="m-0">Registered SSH Keys</h5>
            <div class="ms-auto">
                <button class="btn btn-sm btn-outline-secondary" onclick={refreshKeys}>Refresh</button>
            </div>
        </div>
        {#await keysPromise}
            <div class="p-3 text-center text-muted">
                <span class="spinner-border spinner-border-sm"></span> Loading keys...
            </div>
        {:then keys}
            {#if !keys || keys.length === 0}
                <div class="p-3 text-center text-muted">No active SSH keys registered.</div>
            {:else}
                <div class="row g-0 align-items-center px-3 py-1 border-bottom text-muted small fw-semibold">
                    <div class="col-3">Fingerprint</div>
                    <div class="col-2">Tunnel</div>
                    <div class="col-2">User</div>
                    <div class="col-2">Created</div>
                    <div class="col-2">Expires</div>
                    <div class="col-1 text-end">Actions</div>
                </div>
                {#each keys as key (key.key_id)}
                    <div class="row g-0 align-items-center px-3 py-2 border-bottom">
                        <div class="col-3 font-monospace small d-flex align-items-center">{@render copyCell(key.fingerprint)}</div>
                        <div class="col-2 font-monospace small text-muted d-flex align-items-center">{@render copyCell(key.tunnel_id)}</div>
                        <div class="col-2 font-monospace small text-muted d-flex align-items-center">{@render copyCell(key.user_id)}</div>
                        <div class="col-2 small">{timestampToISODate(key.created_at, true)}</div>
                        <div class="col-2 small">{timestampToISODate(key.expires_at, true)}</div>
                        <div class="col-1 text-end">
                            <button
                                class="btn btn-sm btn-outline-danger"
                                disabled={working}
                                onclick={() => {
                                    selectedKey = key;
                                    confirmDeleteKey = true;
                                }}
                            >
                                Revoke
                            </button>
                        </div>
                    </div>
                {/each}
            {/if}
        {:catch error}
            <div class="alert alert-danger m-2">{error.message}</div>
        {/await}
    </div>
</div>

<style>
    .host-key-fp {
        max-width: 220px;
    }
</style>
