<script lang="ts">
    import type { ChartConfiguration } from "chart.js";
    import { chart } from "./chart";
    import { dateLabel, usd } from "./format";
    import { orderedBackends, seriesColor } from "./palette";
    import { watchTheme } from "./theme.svelte";
    import type { Granularity, Series } from "./types";

    interface Props {
        series: Series;
        granularity: Granularity;
    }

    let { series, granularity }: Props = $props();

    const theme = watchTheme();
    let asTable = $state(false);

    const backends = $derived(orderedBackends(Object.keys(series.backends)));
    const labels = $derived(series.buckets.map((bucket) => dateLabel(bucket, granularity)));
    const totals = $derived(series.buckets.map((_, index) => backends.reduce((sum, backend) => sum + (series.backends[backend][index] ?? 0), 0)));
    const empty = $derived(totals.every((total) => total === 0));
    const unit = $derived(granularity === "day" ? "USD per day" : granularity === "week" ? "USD per week" : "USD per month");

    const config = $derived.by((): ChartConfiguration => {
        const dark = theme.dark;
        const ink = dark ? "#dee2e6" : "#212529";
        const grid = dark ? "rgba(222, 226, 230, 0.12)" : "rgba(33, 37, 41, 0.1)";
        return {
            type: "bar",
            data: {
                labels: $state.snapshot(labels),
                datasets: backends.map((backend, position) => ({
                    label: backend,
                    data: $state.snapshot(series.backends[backend]),
                    backgroundColor: seriesColor(backend, position, dark),
                    borderColor: "transparent",
                    borderWidth: { top: 2 },
                    borderRadius: 2,
                    maxBarThickness: 48,
                })),
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                scales: {
                    x: { stacked: true, grid: { display: false }, ticks: { color: ink, maxRotation: 0, autoSkip: true } },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        grid: { color: grid },
                        border: { display: false },
                        ticks: { color: ink, callback: (value) => usd(Number(value)) },
                    },
                },
                plugins: {
                    legend: { position: "top", align: "end", labels: { color: ink, boxWidth: 10, boxHeight: 10, usePointStyle: true } },
                    tooltip: {
                        callbacks: {
                            label: (item) => ` ${item.dataset.label}: ${usd(Number(item.raw))}`,
                            footer: (items) => `Total ${usd(items.reduce((sum, item) => sum + Number(item.raw), 0))}`,
                        },
                    },
                },
            },
        };
    });
</script>

<div class="panel rounded p-2 p-md-3 h-100 bg-white d-flex flex-column">
    <div class="d-flex justify-content-between align-items-baseline gap-2 flex-wrap">
        <div>
            <h2 class="h6 mb-0">Spend over time, by backend</h2>
            <div class="small text-body-secondary">{unit}</div>
        </div>
        <button type="button" class="btn btn-link btn-sm p-0" onclick={() => (asTable = !asTable)}>
            {asTable ? "View as chart" : "View as table"}
        </button>
    </div>
    {#if empty}
        <div class="flex-grow-1 d-flex align-items-center justify-content-center text-body-secondary py-5">
            No runs.
        </div>
    {:else if asTable}
        <div class="table-responsive rounded overflow-hidden mt-2">
            <table class="table table-sm mb-0">
                <thead>
                    <tr>
                        <th scope="col">Bucket</th>
                        {#each backends as backend (backend)}
                            <th scope="col" class="text-end">{backend}</th>
                        {/each}
                        <th scope="col" class="text-end">Total</th>
                    </tr>
                </thead>
                <tbody>
                    {#each series.buckets as bucket, index (bucket)}
                        <tr>
                            <th scope="row" class="fw-normal">{labels[index]}</th>
                            {#each backends as backend (backend)}
                                <td class="text-end">{usd(series.backends[backend][index])}</td>
                            {/each}
                            <td class="text-end fw-semibold">{usd(totals[index])}</td>
                        </tr>
                    {/each}
                </tbody>
            </table>
        </div>
    {:else}
        <div class="chart-area flex-grow-1 mt-2">
            <canvas use:chart={config} aria-label="Spend over time by backend"></canvas>
        </div>
    {/if}
</div>

<style>
    .chart-area {
        position: relative;
        min-height: 18rem;
    }
</style>
