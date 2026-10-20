<script lang="ts">
    import { slide } from "svelte/transition";
    import { cubicInOut } from "svelte/easing";
    import Fa from "svelte-fa";
    import { faChevronDown, faChevronRight, faFilter, faServer } from "@fortawesome/free-solid-svg-icons";
    import NemesisDetails from "./NemesisDetails.svelte";
    import { descriptionSummary, endTimeLabel, formatNemesisTime, statusClasses, statusLabel } from "./nemesisListing";
    import { rowNavigation } from "./rowNavigation";
    import type { NemesisInfo, NemesisResource } from "./types";

    interface Props {
        nemesis: NemesisInfo;
        resource?: NemesisResource;
        open?: boolean;
        highlighted?: boolean;
        filtered?: boolean;
        statusOnly?: boolean;
        onToggle: () => void;
        onSelectNode?: (name: string) => void;
        onHoverNode?: (name: string | null) => void;
        onFilterNode?: (name: string) => void;
        onFilterStatus?: (status: string) => void;
    }

    let {
        nemesis,
        resource,
        open = false,
        highlighted = false,
        filtered = false,
        statusOnly = false,
        onToggle,
        onSelectNode,
        onHoverNode,
        onFilterNode,
        onFilterStatus,
    }: Props = $props();

    const summary = $derived(descriptionSummary(nemesis.description));
    const inProgress = $derived(nemesis.end_time === 0);
    const status = $derived(statusLabel(nemesis.status));
    const hoverNode = () => onHoverNode?.(nemesis.target_node.name);
    const leaveNode = () => onHoverNode?.(null);

    const toggleFromRow = (event: MouseEvent) => {
        const target = event.target as HTMLElement;
        if (target.closest("button, .time-col") || window.getSelection()?.toString()) {
            return;
        }
        onToggle();
    };

    const toggleFromKey = (event: KeyboardEvent) => {
        if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            onToggle();
        }
    };
</script>

{#snippet nodeChip()}
    <span class="text-muted flex-shrink-0"><Fa icon={faServer} /></span>
    <span class="text-truncate">{nemesis.target_node.name}</span>
{/snippet}

<div class="nemesis-row px-2 py-1" class:bg-white={!highlighted} class:bg-primary-subtle={highlighted} role="rowgroup">
    <div
        class="nemesis-summary row g-2 align-items-center"
        role="row"
        tabindex="-1"
        onclick={toggleFromRow}
        onkeydown={toggleFromKey}
    >
        <div class="col min-w-0" role="cell">
            <button
                type="button"
                class="nemesis-toggle btn btn-link p-0 border-0 text-reset text-decoration-none text-start d-flex align-items-center
                    gap-2 mw-100"
                aria-expanded={open}
                onclick={onToggle}
                use:rowNavigation
            >
                <span class="text-muted flex-shrink-0"><Fa icon={open ? faChevronDown : faChevronRight} /></span>
                <span class="nemesis-name fw-bold text-truncate" title={nemesis.name}>{nemesis.name}</span>
            </button>
            {#if summary}
                <div class="small text-muted text-truncate ps-4" title={nemesis.description}>{summary}</div>
            {/if}
        </div>
        <div class="w-100 d-lg-none" role="presentation"></div>
        <div class="col-auto col-lg-3 min-w-0 d-flex align-items-center gap-1" role="cell">
            {#if onSelectNode}
                <button
                    type="button"
                    class="node-link d-inline-flex align-items-center gap-1 rounded px-2 border-0 text-reset bg-light-two
                        font-monospace small min-w-0"
                    title="Show {nemesis.target_node.name} in Resources"
                    onclick={() => onSelectNode(nemesis.target_node.name)}
                    onmouseenter={hoverNode}
                    onmouseleave={leaveNode}
                    onfocus={hoverNode}
                    onblur={leaveNode}
                >
                    {@render nodeChip()}
                </button>
            {:else}
                <span
                    class="d-inline-flex align-items-center gap-1 rounded px-2 bg-light-two font-monospace small min-w-0"
                    role="presentation"
                    title={nemesis.target_node.name}
                    onmouseenter={hoverNode}
                    onmouseleave={leaveNode}
                >
                    {@render nodeChip()}
                </span>
            {/if}
            {#if onFilterNode}
                <button
                    type="button"
                    class="btn btn-sm btn-link p-0 border-0 flex-shrink-0"
                    class:text-muted={!filtered}
                    title={filtered ? "Show every node" : `Show only ${nemesis.target_node.name}`}
                    aria-label="Filter by {nemesis.target_node.name}"
                    aria-pressed={filtered}
                    onclick={() => onFilterNode(nemesis.target_node.name)}
                >
                    <Fa icon={faFilter} />
                </button>
            {/if}
        </div>
        <div class="col-auto status-col" role="cell">
            {#if onFilterStatus}
                <button
                    type="button"
                    class="badge rounded-pill border-0 {statusClasses(nemesis.status)}"
                    title={statusOnly ? "Show every status" : `Show only ${status.toLowerCase()} nemeses`}
                    aria-label="Filter by status {status}"
                    aria-pressed={statusOnly}
                    onclick={() => onFilterStatus(nemesis.status)}
                >
                    {status}
                </button>
            {:else}
                <span class="badge rounded-pill {statusClasses(nemesis.status)}">{status}</span>
            {/if}
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

    .node-link:hover,
    .node-link:focus-visible {
        text-decoration: underline;
    }

    .nemesis-summary {
        cursor: pointer;
    }

    .nemesis-summary:focus {
        outline: none;
    }

    .nemesis-summary .time-col {
        cursor: text;
    }

    .nemesis-row:has(> .nemesis-summary:hover) {
        background-image: linear-gradient(
            rgba(var(--bs-emphasis-color-rgb), 0.075),
            rgba(var(--bs-emphasis-color-rgb), 0.075)
        );
    }
</style>
