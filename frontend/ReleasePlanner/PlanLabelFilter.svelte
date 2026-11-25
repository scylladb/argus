<script lang="ts">
    import type { LabelCount } from "./planLabels";

    interface Props {
        counts: LabelCount[];
        selected: string[];
        ontoggle: (label: string) => void;
    }

    let { counts, selected, ontoggle }: Props = $props();
</script>

{#if counts.length > 0}
    <div class="d-flex flex-wrap align-items-center gap-1" role="group" aria-label="Filter by label">
        <span class="small text-body-secondary me-1">Labels:</span>
        {#each counts as { label, count } (label)}
            {@const active = selected.includes(label)}
            <button type="button" class="btn btn-sm rounded-pill {active ? 'btn-info' : 'btn-outline-info'}"
                    aria-pressed={active} onclick={() => ontoggle(label)}>
                {label} <span class="small">({count})</span>
            </button>
        {/each}
    </div>
{/if}
