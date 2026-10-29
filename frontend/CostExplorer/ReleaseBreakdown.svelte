<script lang="ts">
    import SortHeader from "./SortHeader.svelte";
    import { integer, share, usd } from "./format";
    import { createSort } from "./sort.svelte";
    import type { Breakdown, BreakdownRow, ReleaseEntry } from "./types";

    interface Props {
        releases: ReleaseEntry[];
        breakdown: Breakdown;
    }

    let { releases, breakdown }: Props = $props();

    type Column = "name" | "runs" | "priced_runs" | "spend" | "cost_per_run";
    const ROWS_SHOWN = 10;
    const sort = createSort<Column>("spend");
    let expanded: Record<string, boolean> = $state({});
    let collapsed: Record<string, boolean> = $state({});

    const total = $derived(releases.reduce((sum, release) => sum + release.spend, 0));
    const value = (row: BreakdownRow, by: Column) => row[by];
    const rowsOf = (release: ReleaseEntry): BreakdownRow[] => {
        const sorted = sort.apply(release.rows, value);
        return expanded[release.id] ? sorted : sorted.slice(0, ROWS_SHOWN);
    };
    const fill = (row: BreakdownRow, release: ReleaseEntry): number =>
        release.spend > 0 ? Math.round((row.spend / release.spend) * 100) : 0;
</script>

<div class="panel rounded p-2 p-md-3 h-100 bg-white">
    <h2 class="h6 mb-0">Cost breakdown by {breakdown}</h2>
    <div class="small text-body-secondary">Total spend per release, by {breakdown}</div>
    {#if releases.length === 0}
        <div class="text-body-secondary py-4">No run started in this range.</div>
    {:else}
        <div class="table-responsive overflow-hidden mt-2">
            <table class="table table-sm table-hover small mb-0">
                <colgroup>
                    <col />
                    <col class="num-col" />
                    <col class="num-col" />
                    <col class="money-col" />
                    <col class="money-col" />
                </colgroup>
                <thead>
                    <tr>
                        <SortHeader {sort} key="name" label={breakdown === "group" ? "Group" : "Test"} />
                        <SortHeader {sort} key="runs" label="Runs" align="end" />
                        <SortHeader {sort} key="priced_runs" label="Priced" align="end" />
                        <SortHeader {sort} key="spend" label="Spend" align="end" />
                        <SortHeader {sort} key="cost_per_run" label="Per run" align="end" />
                    </tr>
                </thead>
                {#each releases as release (release.id)}
                    <tbody class="release">
                        <tr class="release-row">
                            <th scope="rowgroup" colspan="2">
                                <button type="button" class="toggle" aria-expanded={!collapsed[release.id]}
                                    onclick={() => (collapsed[release.id] = !collapsed[release.id])}>
                                    <span class="caret" aria-hidden="true">{collapsed[release.id] ? "▸" : "▾"}</span>
                                    {release.name}
                                    <span class="fw-normal text-body-secondary">· {integer(release.runs)} runs</span>
                                </button>
                            </th>
                            <th scope="rowgroup" class="text-end fw-normal text-body-secondary tabular">{share(release.spend, total)}</th>
                            <th scope="rowgroup" class="text-end tabular">{usd(release.spend)}</th>
                            <th scope="rowgroup"></th>
                        </tr>
                        {#if !collapsed[release.id]}
                            {#each rowsOf(release) as row (row.id ?? "unassigned")}
                                <tr>
                                    <td class="text-truncate name-col">{row.name}</td>
                                    <td class="text-end tabular">{integer(row.runs)}</td>
                                    <td class="text-end tabular">{integer(row.priced_runs)}</td>
                                    <td class="text-end tabular spend-cell" style="--fill: {fill(row, release)}%">{usd(row.spend)}</td>
                                    <td class="text-end tabular">{usd(row.cost_per_run)}</td>
                                </tr>
                            {/each}
                            {#if release.rows.length > ROWS_SHOWN}
                                <tr>
                                    <td colspan="5">
                                        <button type="button" class="btn btn-link btn-sm p-0" onclick={() => (expanded[release.id] = !expanded[release.id])}>
                                            {expanded[release.id] ? "Show fewer" : `Show all ${release.rows.length}`}
                                        </button>
                                    </td>
                                </tr>
                            {/if}
                        {/if}
                    </tbody>
                {/each}
            </table>
        </div>
    {/if}
</div>

<style>
    .num-col {
        width: 4.5rem;
    }

    .money-col {
        width: 6.5rem;
    }

    .name-col {
        max-width: 24rem;
    }

    .release-row > th {
        padding-top: 0.6rem;
    }

    .toggle {
        background: none;
        border: 0;
        padding: 0;
        font: inherit;
        font-weight: 600;
        color: inherit;
        cursor: pointer;
    }

    .caret {
        display: inline-block;
        width: 1rem;
        color: var(--bs-secondary-color);
    }

    .spend-cell {
        background-image: linear-gradient(to left, rgba(var(--bs-primary-rgb), 0.18) var(--fill), transparent var(--fill));
    }

    .tabular {
        font-variant-numeric: tabular-nums;
    }
</style>
