<script lang="ts">
    import ModalWindow from "../Common/ModalWindow.svelte";

    interface CreateForm {
        host: string;
        port: number;
        proxy_user: string;
        target_host: string;
        target_port: number;
        is_active: boolean;
    }

    let {
        working = false,
        onsubmit,
        oncancel,
    }: {
        working?: boolean;
        onsubmit: (form: CreateForm) => void;
        oncancel: () => void;
    } = $props();

    let form = $state<CreateForm>({
        host: "",
        port: 22,
        proxy_user: "argus-proxy",
        target_host: "",
        target_port: 8080,
        is_active: true,
    });

    let attempted = $state(false);

    const HOST_RE = /^[a-zA-Z0-9._-]+$/;
    const validPort = (value: number): boolean => {
        const port = Number(value);
        return Number.isInteger(port) && port >= 1 && port <= 65535;
    };
    const validHost = (value: string): boolean => HOST_RE.test(value.trim());

    const errors = $derived({
        host: !form.host.trim() ? "Host is required." : !validHost(form.host) ? "Invalid hostname." : "",
        port: !validPort(form.port) ? "Port must be between 1 and 65535." : "",
        proxy_user: !form.proxy_user.trim() ? "Proxy user is required." : "",
        target_host: !form.target_host.trim()
            ? "Target host is required."
            : !validHost(form.target_host)
              ? "Invalid host or IP."
              : "",
        target_port: !validPort(form.target_port) ? "Port must be between 1 and 65535." : "",
    });

    const isValid = $derived(Object.values(errors).every((error) => !error));

    const submit = () => {
        attempted = true;
        if (!isValid) return;
        onsubmit({ ...form, port: Number(form.port), target_port: Number(form.target_port) });
    };
</script>

<ModalWindow on:modalClose={oncancel}>
    {#snippet title()}<div>Add Proxy Tunnel</div>{/snippet}
    {#snippet body()}
        <div>
            <div class="d-flex gap-2 mb-3">
                <div class="flex-grow-1">
                    <label class="form-label" for="proxyHost">Host</label>
                    <input
                        id="proxyHost"
                        type="text"
                        class="form-control"
                        class:is-invalid={attempted && errors.host}
                        bind:value={form.host}
                        placeholder="proxy.example.com"
                    />
                    {#if attempted && errors.host}<div class="invalid-feedback">{errors.host}</div>{/if}
                </div>
                <div style="flex: 0 0 8rem;">
                    <label class="form-label" for="proxyPort">Port</label>
                    <input
                        id="proxyPort"
                        type="number"
                        min="1"
                        max="65535"
                        class="form-control"
                        class:is-invalid={attempted && errors.port}
                        bind:value={form.port}
                    />
                    {#if attempted && errors.port}<div class="invalid-feedback">{errors.port}</div>{/if}
                </div>
            </div>

            <div class="mb-3">
                <label class="form-label" for="proxyUser">Proxy User</label>
                <input
                    id="proxyUser"
                    type="text"
                    class="form-control"
                    class:is-invalid={attempted && errors.proxy_user}
                    bind:value={form.proxy_user}
                />
                {#if attempted && errors.proxy_user}<div class="invalid-feedback">{errors.proxy_user}</div>{/if}
            </div>

            <div class="d-flex gap-2 mb-3">
                <div class="flex-grow-1">
                    <label class="form-label" for="targetHost">Target Host (Argus private IP)</label>
                    <input
                        id="targetHost"
                        type="text"
                        class="form-control"
                        class:is-invalid={attempted && errors.target_host}
                        bind:value={form.target_host}
                        placeholder="10.0.0.42"
                    />
                    {#if attempted && errors.target_host}<div class="invalid-feedback">{errors.target_host}</div>{/if}
                </div>
                <div style="flex: 0 0 8rem;">
                    <label class="form-label" for="targetPort">Target Port</label>
                    <input
                        id="targetPort"
                        type="number"
                        min="1"
                        max="65535"
                        class="form-control"
                        class:is-invalid={attempted && errors.target_port}
                        bind:value={form.target_port}
                    />
                    {#if attempted && errors.target_port}<div class="invalid-feedback">{errors.target_port}</div>{/if}
                </div>
            </div>

            <div class="alert alert-secondary py-2 mb-3 small">
                The host key is discovered automatically via <code>ssh-keyscan</code> and stored as a full
                <code>known_hosts</code> entry. A dedicated service user with a fresh API token is created for this
                proxy host.
            </div>

            <div class="form-check form-switch mb-3">
                <input
                    id="proxyActive"
                    class="form-check-input"
                    type="checkbox"
                    role="switch"
                    bind:checked={form.is_active}
                />
                <label class="form-check-label" for="proxyActive">Active immediately</label>
            </div>

            <div class="d-flex align-items-center my-3">
                <button class="btn btn-primary w-75 me-2" disabled={working} onclick={submit}>
                    {#if working}<span class="spinner-border spinner-border-sm me-2"></span>{/if}
                    Save &amp; Provision
                </button>
                <button class="btn btn-secondary w-25" disabled={working} onclick={oncancel}>Cancel</button>
            </div>
        </div>
    {/snippet}
</ModalWindow>
