<script lang="ts">
    import { integer, percent, share, trend, usd } from "./format";
    import type { Tiles } from "./types";

    interface Props {
        tiles: Tiles;
        windowDays: number;
    }

    let { tiles, windowDays }: Props = $props();

    const hasData = $derived(tiles.priced_runs > 0);
    const spendTrend = $derived(trend(tiles.spend, tiles.previous_spend));
    const trendText = $derived.by(() => {
        if (spendTrend.ratio === null) return "No spend in the window before";
        const arrow = spendTrend.direction === "up" ? "▲" : spendTrend.direction === "down" ? "▼" : "●";
        return `${arrow} ${percent(Math.abs(spendTrend.ratio))} vs the previous ${windowDays} days`;
    });
    const known = $derived(
        tiles.runs > 0 ? `Known for ${integer(tiles.priced_runs)} of ${integer(tiles.runs)} runs (${share(tiles.priced_runs, tiles.runs)})` : "No runs in range"
    );
</script>

<div class="row g-2">
    <div class="col-12 col-md-6 col-xl-3">
        <div class="tile rounded p-3 h-100 bg-white">
            <div class="small text-body-secondary">Total Spend</div>
            <div class="value">{hasData ? usd(tiles.spend) : "No data"}</div>
            <div class="small" class:text-danger={spendTrend.direction === "up"} class:text-success={spendTrend.direction === "down"}>
                {hasData ? trendText : known}
            </div>
            {#if hasData}
                <div class="small text-body-secondary">{known}</div>
            {/if}
        </div>
    </div>
    <div class="col-12 col-md-6 col-xl-3">
        <div class="tile rounded p-3 h-100 bg-white">
            <div class="small text-body-secondary">Weekly run rate</div>
            <div class="value">{hasData ? usd(tiles.weekly_run_rate) : "No data"}</div>
            <div class="small text-body-secondary">Weekly rate for this range</div>
        </div>
    </div>
    <div class="col-12 col-md-6 col-xl-3">
        <div class="tile rounded p-3 h-100 bg-white">
            <div class="small text-body-secondary">Errored Runs</div>
            <div class="value">{hasData ? usd(tiles.errored_spend) : "No data"}</div>
            {#if hasData}
                <div class="small text-body-secondary">{share(tiles.errored_spend, tiles.spend)} of total spend</div>
            {/if}
            <div class="small text-body-secondary">Runs that failed due to infrastructure or framework errors</div>
        </div>
    </div>
    <div class="col-12 col-md-6 col-xl-3">
        <div class="tile rounded p-3 h-100 bg-white">
            <div class="small text-body-secondary">Leaked Costs</div>
            <div class="value">{hasData ? usd(tiles.leaked_spend) : "No data"}</div>
            <div class="small text-body-secondary">
                {tiles.leaked_count > 0 ? `${integer(tiles.leaked_count)} resources reaped late` : "No resource outlived its run"}
            </div>
        </div>
    </div>
</div>

<style>
    .value {
        font-size: 1.75rem;
        font-weight: 600;
        line-height: 1.2;
        font-variant-numeric: tabular-nums;
    }
</style>
