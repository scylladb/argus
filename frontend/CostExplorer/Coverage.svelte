<script lang="ts">
    import { integer, share, usd } from "./format";
    import type { CoverageCounts } from "./types";

    interface Props {
        coverage: CoverageCounts;
    }

    let { coverage }: Props = $props();

    const runs = $derived(coverage.complete + coverage.partial + coverage.none);
    const segments = $derived([
        { key: "complete", label: "Complete", count: coverage.complete, css: "bg-success" },
        { key: "partial", label: "Partial", count: coverage.partial, css: "bg-warning" },
        { key: "none", label: "No data", count: coverage.none, css: "bg-secondary" },
    ]);
</script>

<div class="panel rounded p-2 p-md-3 h-100 bg-white d-flex flex-column">
    <h2 class="h6 mb-0">Cost data coverage</h2>
    <div class="small text-body-secondary">Runs in range: {integer(runs)}</div>
    {#if runs === 0}
        <div class="flex-grow-1 d-flex align-items-center text-body-secondary py-4">No run started in this range.</div>
    {:else}
        <div class="headline mt-2">{share(coverage.complete, runs)}</div>
        <div class="small text-body-secondary mb-2">of runs report costs</div>
        <div class="progress-stacked coverage-bar" role="img" aria-label="Coverage of the runs in range">
            {#each segments as segment (segment.key)}
                {#if segment.count > 0}
                    <div class="progress" style="width: {(segment.count / runs) * 100}%">
                        <div class="progress-bar {segment.css}"></div>
                    </div>
                {/if}
            {/each}
        </div>
        <dl class="row g-0 small mt-2 mb-0">
            {#each segments as segment (segment.key)}
                <dt class="col-7 fw-normal d-flex align-items-center gap-2">
                    <span class="swatch rounded-circle {segment.css}"></span>{segment.label}
                </dt>
                <dd class="col-5 text-end mb-0 tabular">{integer(segment.count)} <span class="text-body-secondary">· {share(segment.count, runs)}</span></dd>
            {/each}
            {#if coverage.estimate_only.count > 0}
                <dt class="col-7 fw-normal text-body-secondary ps-4">Estimate only</dt>
                <dd class="col-5 text-end mb-0 tabular text-body-secondary">{integer(coverage.estimate_only.count)} · {usd(coverage.estimate_only.spend)}</dd>
            {/if}
        </dl>
    {/if}
    <div class="small text-body-secondary mt-auto pt-3">
        A run is partial when a terminated resource reported no cost. An estimate is not counted as spend.
    </div>
</div>

<style>
    .headline {
        font-size: 2rem;
        font-weight: 600;
        line-height: 1.1;
        font-variant-numeric: tabular-nums;
    }

    .coverage-bar {
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
