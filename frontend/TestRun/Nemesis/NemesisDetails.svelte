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

    const reason = $derived(reasonLabel(nemesis.status));
    const canCopy = typeof navigator !== "undefined" && Boolean(navigator.clipboard);
</script>

<div class="p-2 rounded border bg-light-three">
    <div class="row g-3">
        <div class="col-12 col-lg-6">
            <div class="fw-semibold mb-1">Nemesis</div>
            <dl class="row g-0 mb-0 small">
                <dt class="col-4">Class</dt>
                <dd class="col-8 mb-1 font-monospace text-break">{nemesis.class_name}</dd>
                <dt class="col-4">Name</dt>
                <dd class="col-8 mb-1 text-break">{nemesis.name}</dd>
                <dt class="col-4">Status</dt>
                <dd class="col-8 mb-1">
                    <span class="badge rounded-pill {statusClasses(nemesis.status)}">{statusLabel(nemesis.status)}</span>
                </dd>
                {#if nemesis.duration > 0}
                    <dt class="col-4">Duration</dt>
                    <dd class="col-8 mb-1">{humanizeDuration(nemesis.duration * 1000, { largest: 2, round: true })}</dd>
                {/if}
            </dl>
        </div>
        <div class="col-12 col-lg-6">
            <div class="fw-semibold mb-1">Target node</div>
            <dl class="row g-0 mb-0 small">
                <dt class="col-4">Name</dt>
                <dd class="col-8 mb-1 font-monospace text-break">{nemesis.target_node.name}</dd>
                <dt class="col-4">Public IP</dt>
                <dd class="col-8 mb-1 font-monospace">{nemesis.target_node.ip ?? "—"}</dd>
                <dt class="col-4">Private IP</dt>
                <dd class="col-8 mb-1 font-monospace">
                    {#if resource}{resource.instance_info.private_ip}{:else}<span class="text-muted">not found</span>{/if}
                </dd>
                <dt class="col-4">State</dt>
                <dd class="col-8 mb-1">
                    {#if resource}{resource.state}{:else}<span class="text-muted">not found</span>{/if}
                </dd>
                <dt class="col-4">Shards</dt>
                <dd class="col-8 mb-1">{nemesis.target_node.shards ?? "—"}</dd>
            </dl>
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
                            onclick={() => navigator.clipboard.writeText(nemesis.stack_trace)}
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
