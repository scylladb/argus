<script lang="ts">
    import { slide } from "svelte/transition";
    import { cubicInOut } from "svelte/easing";
    import Fa from "svelte-fa";
    import { faChevronDown, faChevronRight, faServer } from "@fortawesome/free-solid-svg-icons";
    import NemesisDetails from "./NemesisDetails.svelte";
    import { descriptionSummary, endTimeLabel, formatNemesisTime, statusClasses, statusLabel } from "./nemesisListing";
    import type { NemesisInfo, NemesisResource } from "./types";

    interface Props {
        nemesis: NemesisInfo;
        resource?: NemesisResource;
        open?: boolean;
        onToggle: () => void;
    }

    let { nemesis, resource, open = false, onToggle }: Props = $props();

    const summary = $derived(descriptionSummary(nemesis.description));
    const inProgress = $derived(nemesis.end_time === 0);
</script>

<div class="rounded border bg-white shadow-sm px-2 py-1" role="rowgroup">
    <div class="row g-2 align-items-center" role="row">
        <div class="col min-w-0" role="cell">
            <button
                type="button"
                class="btn btn-link p-0 border-0 text-reset text-decoration-none text-start d-flex align-items-center gap-2 mw-100"
                aria-expanded={open}
                onclick={onToggle}
            >
                <span class="text-muted flex-shrink-0"><Fa icon={open ? faChevronDown : faChevronRight} /></span>
                <span class="fw-bold text-truncate" title={nemesis.name}>{nemesis.name}</span>
            </button>
            {#if summary}
                <div class="small text-muted text-truncate ps-4" title={nemesis.description}>{summary}</div>
            {/if}
        </div>
        <div class="w-100 d-lg-none" role="presentation"></div>
        <div class="col-auto col-lg-3 min-w-0" role="cell">
            <span
                class="d-inline-flex align-items-center gap-1 rounded px-2 bg-light-two font-monospace small mw-100"
                title={nemesis.target_node.name}
            >
                <span class="text-muted flex-shrink-0"><Fa icon={faServer} /></span>
                <span class="text-truncate">{nemesis.target_node.name}</span>
            </span>
        </div>
        <div class="col-auto status-col" role="cell">
            <span class="badge rounded-pill {statusClasses(nemesis.status)}">{statusLabel(nemesis.status)}</span>
        </div>
        <div class="col-auto time-col small text-nowrap" role="cell">{formatNemesisTime(nemesis.start_time)}</div>
        <div class="col-auto time-col small text-nowrap" class:text-muted={inProgress} class:fst-italic={inProgress} role="cell">
            {endTimeLabel(nemesis)}
        </div>
    </div>
    {#if open}
        <div class="mt-2" role="row" transition:slide={{ duration: 200, easing: cubicInOut }}>
            <div role="cell"><NemesisDetails {nemesis} {resource} /></div>
        </div>
    {/if}
</div>

<style>
    .min-w-0 {
        min-width: 0;
    }
</style>
