<script lang="ts">
    import SortHeader from "./SortHeader.svelte";
    import { integer, percent, usd } from "./format";
    import { createSort } from "./sort.svelte";
    import type { SpotLocation, SpotTerminations } from "./types";

    interface Props {
        terminations: SpotTerminations;
    }

    let { terminations }: Props = $props();

    type Column = "backend" | "region" | "count" | "spend";
    const sort = createSort<Column>("count");
    const sorted = $derived(sort.apply(terminations.by_location, (location: SpotLocation, by: Column) => location[by]));
</script>

<div class="panel rounded p-2 p-md-3 bg-white">
    <h2 class="h6 mb-0">Spot terminations</h2>
    <div class="small text-body-secondary">Total of pre-empted runs</div>
    {#if terminations.spot_runs === 0}
        <div class="text-body-secondary py-4">No spot run in this range.</div>
    {:else if terminations.count === 0}
        <div class="text-body-secondary py-4">None of the {integer(terminations.spot_runs)} spot runs was reclaimed.</div>
    {:else}
        <div class="row g-2 mt-1">
            <div class="col-4">
                <div class="small text-body-secondary">Reclaimed</div>
                <div class="figure">{integer(terminations.count)}</div>
            </div>
            <div class="col-4">
                <div class="small text-body-secondary">Of spot runs</div>
                <div class="figure">{percent(terminations.rate)}</div>
            </div>
            <div class="col-4">
                <div class="small text-body-secondary">Spent on them</div>
                <div class="figure">{usd(terminations.spend)}</div>
            </div>
        </div>
        <div class="rounded overflow-hidden mt-2">
        <table class="table table-sm small mb-0">
            <thead>
                <tr>
                    <SortHeader {sort} key="backend" label="Backend" />
                    <SortHeader {sort} key="region" label="Region" />
                    <SortHeader {sort} key="count" label="Runs" align="end" />
                    <SortHeader {sort} key="spend" label="Spend" align="end" />
                </tr>
            </thead>
            <tbody>
                {#each sorted as location (`${location.backend}/${location.region}`)}
                    <tr>
                        <td>{location.backend ?? "unknown"}</td>
                        <td>{location.region ?? "—"}</td>
                        <td class="text-end tabular">{integer(location.count)}</td>
                        <td class="text-end tabular">{usd(location.spend)}</td>
                    </tr>
                {/each}
            </tbody>
        </table>
        </div>
    {/if}
</div>

<style>
    .figure {
        font-size: 1.25rem;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
    }

    .tabular {
        font-variant-numeric: tabular-nums;
    }
</style>
