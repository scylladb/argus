<script lang="ts">
    import { integer, share, usd } from "./format";
    import { TIER_COLORS } from "./palette";
    import { watchTheme } from "./theme.svelte";
    import type { TierSplit } from "./types";

    interface Props {
        tiers: { spot: TierSplit; on_demand: TierSplit; untiered: TierSplit };
    }

    let { tiers }: Props = $props();

    const theme = watchTheme();
    const total = $derived(tiers.spot.spend + tiers.on_demand.spend + tiers.untiered.spend);
    const rows = $derived.by(() => {
        const colors = theme.dark ? TIER_COLORS.dark : TIER_COLORS.light;
        return [
            { key: "spot", label: "Spot", split: tiers.spot, color: colors.spot },
            { key: "on_demand", label: "On-demand", split: tiers.on_demand, color: colors.on_demand },
            { key: "untiered", label: "Unknown tier", split: tiers.untiered, color: colors.untiered },
        ].filter((row) => row.split.items > 0 || row.split.spend > 0);
    });
</script>

<div class="panel rounded p-2 p-md-3 bg-white">
    <h2 class="h6 mb-0">Spot vs On Demand</h2>
    <div class="small text-body-secondary">Spend per tier</div>
    {#if total === 0}
        <div class="text-body-secondary py-4">No priced resource in this range.</div>
    {:else}
        <div class="progress-stacked tier-bar mt-3" role="img" aria-label="Spend per pricing tier">
            {#each rows as row (row.key)}
                {#if row.split.spend > 0}
                    <div class="progress" style="width: {(row.split.spend / total) * 100}%">
                        <div class="progress-bar" style="background-color: {row.color}"></div>
                    </div>
                {/if}
            {/each}
        </div>
        <table class="table table-sm table-borderless small mt-2 mb-0">
            <tbody>
                {#each rows as row (row.key)}
                    <tr>
                        <td class="ps-0">
                            <span class="swatch rounded-circle me-2" style="background-color: {row.color}"></span>{row.label}
                        </td>
                        <td class="text-end tabular">{usd(row.split.spend)}</td>
                        <td class="text-end text-body-secondary tabular">{share(row.split.spend, total)}</td>
                        <td class="text-end text-body-secondary tabular pe-0">{integer(row.split.items)} resources</td>
                    </tr>
                {/each}
            </tbody>
        </table>
    {/if}
</div>

<style>
    .tier-bar {
        height: 0.75rem;
        gap: 2px;
    }

    .swatch {
        display: inline-block;
        width: 0.6rem;
        height: 0.6rem;
    }

    .tabular {
        font-variant-numeric: tabular-nums;
    }
</style>
