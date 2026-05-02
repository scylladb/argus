<script>
    import Fa from "svelte-fa";
    import { faTimes, faCopy } from "@fortawesome/free-solid-svg-icons";
    import ModalWindow from "../Common/ModalWindow.svelte";
    import { timestampToISODate } from "../Common/DateUtils";

    const ADMIN_API = "/admin/api/v1";

    const emptyForm = () => ({
        host: "",
        port: 22,
        proxy_user: "argus-proxy",
        target_host: "",
        target_port: 8080,
        is_active: true,
    });

    let lastError = $state("");
    let lastNotice = $state("");
    let working = $state(false);

    let showCreateForm = $state(false);
    let createForm = $state(emptyForm());
    let createdConfig = $state(null);

    let confirmDeleteKey = $state(false);
    let selectedKey = $state(null);

    let confirmToggleActive = $state(false);
    let toggleTarget = $state(null);

    let confirmDeleteConfig = $state(false);
    let deleteTarget = $state(null);

    let activeFilter = $state("all");

    const fetchJson = async (url, init) => {
        const response = await fetch(url, init);
        const data = await response.json().catch(() => null);
        if (!data) {
            throw new Error(`HTTP ${response.status} on ${url}`);
        }
        if (data.status !== "ok") {
            const message =
                data.message ?? data.response?.arguments?.[0] ?? data.response?.message ?? `HTTP ${response.status}`;
            throw new Error(message);
        }
        return data.response;
    };

    const loadConfigs = async () => {
        const params = new URLSearchParams();
        if (activeFilter === "active") params.set("active_only", "true");
        if (activeFilter === "inactive") params.set("active_only", "false");
        const qs = params.toString();
        return await fetchJson(`${ADMIN_API}/proxy-tunnel/configs${qs ? `?${qs}` : ""}`);
    };

    const loadKeys = async () => await fetchJson(`${ADMIN_API}/ssh/keys`);

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
            const config = await fetchJson(`${ADMIN_API}/proxy-tunnel/config`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            createdConfig = config;
            lastNotice = `Proxy tunnel ${config.host}:${config.port} provisioned.`;
            resetForm();
            refreshConfigs();
        } catch (error) {
            lastError = error.message;
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
        } catch (error) {
            lastError = error.message;
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
            await fetchJson(`${ADMIN_API}/proxy-tunnel/config/${deleteTarget.id}`, { method: "DELETE" });
            lastNotice = `Proxy tunnel ${deleteTarget.host}:${deleteTarget.port} deleted.`;
            refreshConfigs();
            refreshKeys();
        } catch (error) {
            lastError = error.message;
        } finally {
            working = false;
            confirmDeleteConfig = false;
            deleteTarget = null;
        }
    };

    const submitDeleteKey = async () => {
        if (!selectedKey) return;
        try {
            working = true;
            await fetchJson(`${ADMIN_API}/ssh/keys/${selectedKey.key_id}`, { method: "DELETE" });
            refreshKeys();
        } catch (error) {
            lastError = error.message;
        } finally {
            working = false;
            confirmDeleteKey = false;
            selectedKey = null;
        }
    };

    const copyToClipboard = async (value, label) => {
        try {
            await navigator.clipboard.writeText(value);
            lastNotice = `${label} copied to clipboard.`;
        } catch (error) {
            lastError = `Could not copy ${label.toLowerCase()}: ${error.message}`;
        }
    };

    const formatDate = (raw) => {
        if (!raw) return "—";
        const ts = Date.parse(raw);
        if (Number.isNaN(ts)) return raw;
        return timestampToISODate(ts, true);
    };

    const truncate = (value, head = 14, tail = 8) => {
        if (!value) return "—";
        const trimmed = String(value).trim();
        if (trimmed.length <= head + tail + 1) return trimmed;
        return `${trimmed.slice(0, head)}…${trimmed.slice(-tail)}`;
    };

    const knownHostSummary = (entry) => {
        if (!entry) return { type: "—", short: "—" };
        const parts = String(entry).trim().split(/\s+/);
        if (parts.length < 3) return { type: "?", short: truncate(entry) };
        return { type: parts[1], short: truncate(parts[2], 10, 6) };
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
    <ModalWindow on:modalClose={() => (confirmDeleteConfig = false)}>
        {#snippet title()}<div>Delete proxy tunnel</div>{/snippet}
        {#snippet body()}
            <div>
                <div>
                    Permanently delete <span class="fw-bold">{deleteTarget.host}:{deleteTarget.port}</span> and its service user?
                </div>
                <div class="text-muted small mt-2">
                    The associated API token is invalidated. The proxy host will refuse new connections after its <code>argus-cli</code> token stops working.
                </div>
                <div class="d-flex align-items-center my-3">
                    <button class="btn btn-danger w-75 me-2" disabled={working} onclick={submitDeleteConfig}>Delete</button>
                    <button class="btn btn-secondary w-25" disabled={working} onclick={() => (confirmDeleteConfig = false)}>Cancel</button>
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
    {#if lastError}
        <div class="alert alert-danger d-flex align-items-center">
            <div>{lastError}</div>
            <div class="ms-auto">
                <button class="btn btn-sm" aria-label="Dismiss error" onclick={() => (lastError = "")}><Fa icon={faTimes} /></button>
            </div>
        </div>
    {/if}
    {#if lastNotice}
        <div class="alert alert-success d-flex align-items-center">
            <div>{lastNotice}</div>
            <div class="ms-auto">
                <button class="btn btn-sm" aria-label="Dismiss notice" onclick={() => (lastNotice = "")}><Fa icon={faTimes} /></button>
            </div>
        </div>
    {/if}

    {#if createdConfig?.api_token}
        <div class="alert alert-info">
            <div class="fw-bold mb-1">Service user API token (shown once)</div>
            <div class="d-flex align-items-center">
                <code class="text-break flex-grow-1">{createdConfig.api_token}</code>
                <button
                    class="btn btn-sm btn-outline-primary ms-2"
                    onclick={() => copyToClipboard(createdConfig.api_token, "API token")}
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
                <div class="table-responsive">
                    <table class="table table-sm align-middle mb-0">
                        <thead>
                            <tr>
                                <th>Host</th>
                                <th>Proxy User</th>
                                <th>Target</th>
                                <th>Host Key</th>
                                <th>Service User</th>
                                <th>Status</th>
                                <th class="text-end">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each configs as config (config.id)}
                                {@const knownHost = knownHostSummary(config.host_key_fingerprint)}
                                <tr>
                                    <td class="font-monospace">{config.host}:{config.port}</td>
                                    <td class="font-monospace">{config.proxy_user}</td>
                                    <td class="font-monospace">{config.target_host}:{config.target_port}</td>
                                    <td class="font-monospace small" title={config.host_key_fingerprint}>
                                        <span class="badge bg-light text-dark border me-1">{knownHost.type}</span>{knownHost.short}
                                        <button
                                            class="btn btn-link btn-sm p-0 ms-1 align-baseline"
                                            title="Copy known_hosts entry"
                                            aria-label="Copy known_hosts entry"
                                            onclick={() => copyToClipboard(config.host_key_fingerprint, "known_hosts entry")}
                                        >
                                            <Fa icon={faCopy} />
                                        </button>
                                    </td>
                                    <td class="font-monospace small text-muted" title={config.service_user_id ?? ""}>
                                        {config.service_user_id ? truncate(config.service_user_id, 8, 4) : "—"}
                                    </td>
                                    <td>
                                        {#if config.is_active}
                                            <span class="badge bg-success">Active</span>
                                        {:else}
                                            <span class="badge bg-secondary">Inactive</span>
                                        {/if}
                                    </td>
                                    <td class="text-end">
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
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            {/if}
        {:catch error}
            <div class="alert alert-danger m-2">{error.message}</div>
        {/await}
    </div>

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
                <div class="table-responsive">
                    <table class="table table-sm align-middle mb-0">
                        <thead>
                            <tr>
                                <th>Fingerprint</th>
                                <th>Tunnel</th>
                                <th>User</th>
                                <th>Created</th>
                                <th>Expires</th>
                                <th class="text-end">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each keys as key (key.key_id)}
                                <tr>
                                    <td class="font-monospace small" title={key.fingerprint}>{truncate(key.fingerprint)}</td>
                                    <td class="font-monospace small text-muted" title={key.tunnel_id}>{truncate(key.tunnel_id, 8, 4)}</td>
                                    <td class="font-monospace small text-muted" title={key.user_id}>{truncate(key.user_id, 8, 4)}</td>
                                    <td class="small">{formatDate(key.created_at)}</td>
                                    <td class="small">{formatDate(key.expires_at)}</td>
                                    <td class="text-end">
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
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
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
</style>
