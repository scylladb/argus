<script lang="ts">
    import Fa from "svelte-fa";
    import { faCopy } from "@fortawesome/free-solid-svg-icons";
    import humanizeDuration from "humanize-duration";
    import { reasonLabel, statusClasses, statusLabel } from "./nemesisListing";
    import type { NemesisInfo, NemesisResource } from "./types";

    interface Props {
        nemesis: NemesisInfo;
        resource?: NemesisResource;
    }

    let { nemesis, resource }: Props = $props();

    const uid = $props.id();
    const reason = $derived(reasonLabel(nemesis.status));
    const canCopy = typeof navigator !== "undefined" && Boolean(navigator.clipboard);
    const copy = (text: string) => navigator.clipboard.writeText(text);
</script>

{#snippet field(id: string, label: string, value: string | null, mono = false, placeholder = "")}
    <div class="input-group input-group-sm detail-group">
        <label class="input-group-text detail-label" for="{uid}-{id}">{label}</label>
        <input
            id="{uid}-{id}"
            class="form-control"
            class:font-monospace={mono}
            type="text"
            value={value ?? ""}
            {placeholder}
            disabled
        />
        {#if canCopy && value}
            <button
                type="button"
                class="btn btn-outline-secondary copy-button"
                title="Copy the {label.toLowerCase()}"
                aria-label="Copy {label}"
                onclick={() => copy(value)}
            >
                <Fa icon={faCopy} />
            </button>
        {/if}
    </div>
{/snippet}

<div class="p-2 rounded border bg-light-three">
    <div class="row g-3">
        <div class="col-12 col-lg-6 d-flex flex-column gap-1">
            <div class="fw-semibold">Nemesis</div>
            {@render field("class", "Class", nemesis.class_name, true)}
            {@render field("name", "Name", nemesis.name)}
            <div class="input-group input-group-sm detail-group">
                <span class="input-group-text detail-label">Status</span>
                <span class="form-control d-flex align-items-center bg-body-secondary">
                    <span class="badge rounded-pill {statusClasses(nemesis.status)}">{statusLabel(nemesis.status)}</span>
                </span>
            </div>
            {#if nemesis.duration > 0}
                {@render field("duration", "Duration", humanizeDuration(nemesis.duration * 1000, { largest: 2, round: true }))}
            {/if}
        </div>
        <div class="col-12 col-lg-6 d-flex flex-column gap-1">
            <div class="fw-semibold">Target node</div>
            {@render field("node", "Name", nemesis.target_node.name, true)}
            {@render field("public-ip", "Public IP", nemesis.target_node.ip, true)}
            {@render field("private-ip", "Private IP", resource?.instance_info.private_ip ?? null, true, "not found")}
            {@render field("state", "State", resource?.state ?? null, false, "not found")}
            {@render field("shards", "Shards", nemesis.target_node.shards === null ? null : String(nemesis.target_node.shards))}
        </div>
        {#if nemesis.description}
            <div class="col-12">
                <div class="fw-semibold mb-1">Description</div>
                <p class="description small mb-0">{nemesis.description}</p>
            </div>
        {/if}
        {#if nemesis.stack_trace}
            <div class="col-12">
                <div class="d-flex align-items-center gap-2 mb-1">
                    <span class="fw-semibold">{reason}</span>
                    {#if canCopy}
                        <button
                            type="button"
                            class="btn btn-sm btn-outline-secondary"
                            title="Copy the {reason.toLowerCase()}"
                            onclick={() => copy(nemesis.stack_trace)}
                        >
                            <Fa icon={faCopy} /> Copy
                        </button>
                    {/if}
                </div>
                <pre class="reason font-monospace small p-2 rounded bg-light-two mb-0">{nemesis.stack_trace}</pre>
            </div>
        {/if}
    </div>
</div>

<style>
    .detail-label {
        width: 6.5rem;
    }

    .detail-group .form-control:disabled {
        color: var(--bs-body-color);
    }

    .copy-button {
        opacity: 0;
    }

    .detail-group:hover .copy-button,
    .detail-group:focus-within .copy-button,
    .copy-button:focus-visible {
        opacity: 1;
    }

    .description {
        white-space: pre-line;
    }

    .reason {
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        max-height: 50vh;
        overflow: auto;
    }
</style>
