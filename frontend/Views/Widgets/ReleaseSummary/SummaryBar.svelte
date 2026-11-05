<script lang="ts">
    import { barSegments, type StatusGroup } from "./summaryUtils";
    import type { SummaryCounts } from "./types";

    interface Props {
        counts: SummaryCounts;
        label: string;
        compact?: boolean;
        onSelect?: (group: StatusGroup) => void;
    }

    let { counts, label, compact = false, onSelect }: Props = $props();

    const segments = $derived(barSegments(counts));
</script>

<div class="summary-bar d-flex rounded overflow-hidden bg-body-secondary" class:compact role="group" aria-label={label}>
    {#each segments as segment (segment.group)}
        {#if onSelect}
            <button
                type="button"
                class="segment border-0 p-0 {segment.css}"
                style="width: {segment.percent}%"
                title="{segment.count} {segment.label.toLowerCase()}"
                aria-label="Show the {segment.count} {segment.label.toLowerCase()} tests"
                onclick={() => onSelect(segment.group)}
            >
                {#if !compact && segment.percent >= 6}{segment.count}{/if}
            </button>
        {:else}
            <span class="segment {segment.css}" style="width: {segment.percent}%" title="{segment.count} {segment.label.toLowerCase()}">
                {#if !compact && segment.percent >= 6}{segment.count}{/if}
            </span>
        {/if}
    {/each}
</div>

<style>
    .summary-bar {
        height: 1.25rem;
        min-width: 8rem;
    }

    .summary-bar.compact {
        height: 0.5rem;
        min-width: 5rem;
    }

    .segment {
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
        line-height: 1;
        overflow: hidden;
        white-space: nowrap;
    }

    button.segment:hover,
    button.segment:focus-visible {
        filter: brightness(0.85);
    }
</style>
