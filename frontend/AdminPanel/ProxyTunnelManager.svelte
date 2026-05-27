<script lang="ts">
    import Fa from "svelte-fa";
    import { faTimes, faCopy } from "@fortawesome/free-solid-svg-icons";
    import ModalWindow from "../Common/ModalWindow.svelte";
    import { timestampToISODate } from "../Common/DateUtils";
    import { fetchJson, truncate, knownHostSummary, copyToClipboard } from "../Common/ProxyUtils";
    import { sendMessage } from "../Stores/AlertStore";

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

    const emptyForm = (): CreateForm => ({
        host: "",
        port: 22,
        proxy_user: "argus-proxy",
        target_host: "",
        target_port: 8080,
        is_active: true,
    });

    let working = $state(false);

    let showCreateForm = $state(false);
    let createForm = $state<CreateForm>(emptyForm());
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
        const params = new URLSearchParams();
        if (activeFilter === "active") params.set("active_only", "true");
        if (activeFilter === "inactive") params.set("active_only", "false");
        const qs = params.toString();
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

    const resetForm = () => {
        createForm = emptyForm();
        showCreateForm = false;
    };

    const submitCreate = async () => {
        try {
            working = true;
            const payload = {
                ...createForm,
                port: Number(createForm.port),
                target_port: Number(createForm.target_port),
            };
            const config = await fetchJson<TunnelConfig>(`${ADMIN_API}/proxy-tunnel/config`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            showCreateForm = false;
            createForm = emptyForm();
            createdConfig = config;
            sendMessage("success", `Proxy tunnel ${config.host}:${config.port} provisioned.`, "ProxyTunnelManager::submitCreate");
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
            const params = deleteServiceUser ? "?delete_user=true" : "";
            await fetchJson(`${ADMIN_API}/proxy-tunnel/config/${deleteTarget.id}${params}`, { method: "DELETE" });
            const userMsg = deleteServiceUser ? " and service user" : "";
            sendMessage("success", `Proxy tunnel ${deleteTarget.host}:${deleteTarget.port}${userMsg} deleted.`, "ProxyTunnelManager::submitDeleteConfig");
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
            sendMessage("success", "SSH key revoked.", "ProxyTunnelManager::submitDeleteKey");
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

    const formatDate = (raw: string | null | undefined): string => {
        if (!raw) return "—";
        const ts = Date.parse(raw);
        if (Number.isNaN(ts)) return raw;
        return timestampToISODate(ts, true);
    };

    const formIsValid = $derived(
        Boolean(createForm.host && createForm.target_host && createForm.proxy_user && createForm.port && createForm.target_port),
    );
</script>

{#if showCreateForm}
    <ModalWindow on:modalClose={resetForm}>
        {#snippet title()}<div>Add Proxy Tunnel</div>{/snippet}
        {#snippet body()}
            <div>
                <div class="row g-2">
                    <div class="col-md-8">
                        <label class="form-label" for="proxyHost">Host</label>
                        <input id="proxyHost" type="text" class="form-control" bind:value={createForm.host} placeholder="proxy.example.com" />
                    </div>
                    <div class="col-md-4">
                        <label class="form-label" for="proxyPort">Port</label>
                        <input id="proxyPort" type="number" min="1" max="65535" class="form-control" bind:value={createForm.port} />
                    </div>
                    <div class="col-md-12">
                        <label class="form-label" for="proxyUser">Proxy User</label>
                        <input id="proxyUser" type="text" class="form-control" bind:value={createForm.proxy_user} />
                    </div>
                    <div class="col-md-8">
                        <label class="form-label" for="targetHost">Target Host (Argus private IP)</label>
                        <input id="targetHost" type="text" class="form-control" bind:value={createForm.target_host} placeholder="10.0.0.42" />
                    </div>
                    <div class="col-md-4">
                        <label class="form-label" for="targetPort">Target Port</label>
                        <input id="targetPort" type="number" min="1" max="65535" class="form-control" bind:value={createForm.target_port} />
                    </div>
                    <div class="col-md-12">
                        <div class="alert alert-secondary py-2 mb-0 small">
                            The host key is discovered automatically via <code>ssh-keyscan</code> and stored as a full
                            <code>known_hosts</code> entry. A dedicated service user with a fresh API token is created for
                            this proxy host.
                        </div>
                    </div>
                    <div class="col-md-12">
                        <div class="form-check form-switch">
                            <input id="proxyActive" class="form-check-input" type="checkbox" role="switch" bind:checked={createForm.is_active} />
                            <label class="form-check-label" for="proxyActive">Active immediately</label>
                        </div>
                    </div>
                </div>
                <div class="d-flex align-items-center my-3">
                    <button
                        class="btn btn-primary w-75 me-2"
                        disabled={working || !formIsValid}
                        onclick={submitCreate}
                    >
                        {#if working}<span class="spinner-border spinner-border-sm me-2"></span>{/if}
                        Save & Provision
                    </button>
                    <button class="btn btn-secondary w-25" disabled={working} onclick={resetForm}>Cancel</button>
                </div>
            </div>
        {/snippet}
    </ModalWindow>
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
                        The service user <code>proxy-tunnel-{deleteTarget.host}</code> will be permanently removed.
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
                    Revoke key <span class="font-monospace">{truncate(selectedKey.fingerprint)}</span>?
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
                    onclick={() => copyToClipboard(createdConfig!.api_token!, "API token", "ProxyTunnelManager::copyToClipboard")}
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
                    onclick={() => {
                        createForm = emptyForm();
                        showCreateForm = true;
                    }}
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
                <!-- Header row -->
                <div class="d-flex align-items-center px-3 py-1 border-bottom text-muted small fw-semibold config-row">
                    <div class="col-host font-monospace">Host</div>
                    <div class="col-user">Proxy User</div>
                    <div class="col-target font-monospace">Target</div>
                    <div class="col-hostkey">Host Key</div>
                    <div class="col-svcuser">Service User</div>
                    <div class="col-status">Status</div>
                    <div class="col-actions ms-auto text-end">Actions</div>
                </div>
                <ul class="list-group list-group-flush rounded">
                    {#each configs as config (config.id)}
                        {@const kh = knownHostSummary(config.host_key_fingerprint)}
                        <li class="list-group-item">
                            <div class="d-flex align-items-center config-row">
                                <div class="col-host font-monospace">{config.host}:{config.port}</div>
                                <div class="col-user font-monospace small">{config.proxy_user}</div>
                                <div class="col-target font-monospace small">{config.target_host}:{config.target_port}</div>
                                <div class="col-hostkey font-monospace small" title={config.host_key_fingerprint}>
                                    <span class="badge bg-light text-dark border me-1">{kh.type}</span>{kh.short}
                                    <button
                                        class="btn btn-link btn-sm p-0 ms-1 align-baseline"
                                        title="Copy known_hosts entry"
                                        aria-label="Copy known_hosts entry"
                                        onclick={() => copyToClipboard(config.host_key_fingerprint ?? "", "known_hosts entry", "ProxyTunnelManager::copyToClipboard")}
                                    >
                                        <Fa icon={faCopy} />
                                    </button>
                                </div>
                                <div class="col-svcuser font-monospace small text-muted" title={config.service_user_id ?? ""}>
                                    {config.service_user_id ? truncate(config.service_user_id, 8, 4) : "—"}
                                </div>
                                <div class="col-status">
                                    {#if config.is_active}
                                        <span class="badge bg-success">Active</span>
                                    {:else}
                                        <span class="badge bg-secondary">Inactive</span>
                                    {/if}
                                </div>
                                <div class="col-actions ms-auto text-end">
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
                        </li>
                    {/each}
                </ul>
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
                <!-- Header row -->
                <div class="d-flex align-items-center px-3 py-1 border-bottom text-muted small fw-semibold key-row">
                    <div class="col-fp font-monospace">Fingerprint</div>
                    <div class="col-tunnel">Tunnel</div>
                    <div class="col-keyuser">User</div>
                    <div class="col-created">Created</div>
                    <div class="col-expires">Expires</div>
                    <div class="col-keyactions ms-auto text-end">Actions</div>
                </div>
                <ul class="list-group list-group-flush rounded">
                    {#each keys as key (key.key_id)}
                        <li class="list-group-item">
                            <div class="d-flex align-items-center key-row">
                                <div class="col-fp font-monospace small" title={key.fingerprint}>{truncate(key.fingerprint)}</div>
                                <div class="col-tunnel font-monospace small text-muted" title={key.tunnel_id}>{truncate(key.tunnel_id, 8, 4)}</div>
                                <div class="col-keyuser font-monospace small text-muted" title={key.user_id}>{truncate(key.user_id, 8, 4)}</div>
                                <div class="col-created small">{formatDate(key.created_at)}</div>
                                <div class="col-expires small">{formatDate(key.expires_at)}</div>
                                <div class="col-keyactions ms-auto text-end">
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
                        </li>
                    {/each}
                </ul>
            {/if}
        {:catch error}
            <div class="alert alert-danger m-2">{error.message}</div>
        {/await}
    </div>
</div>

<style>
    .text-break {
        word-break: break-all;
    }

    /* Config table columns */
    .config-row .col-host    { flex: 0 0 18%; min-width: 0; }
    .config-row .col-user    { flex: 0 0 12%; min-width: 0; }
    .config-row .col-target  { flex: 0 0 16%; min-width: 0; }
    .config-row .col-hostkey { flex: 0 0 18%; min-width: 0; }
    .config-row .col-svcuser { flex: 0 0 12%; min-width: 0; }
    .config-row .col-status  { flex: 0 0 8%;  min-width: 0; }
    .config-row .col-actions { flex: 0 0 16%; min-width: 0; }

    /* Key table columns */
    .key-row .col-fp         { flex: 0 0 28%; min-width: 0; }
    .key-row .col-tunnel     { flex: 0 0 16%; min-width: 0; }
    .key-row .col-keyuser    { flex: 0 0 16%; min-width: 0; }
    .key-row .col-created    { flex: 0 0 14%; min-width: 0; }
    .key-row .col-expires    { flex: 0 0 14%; min-width: 0; }
    .key-row .col-keyactions { flex: 0 0 12%; min-width: 0; }
</style>
