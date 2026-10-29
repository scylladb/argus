<script lang="ts">
    import { StatusBadgeCSSClassMap } from "../Common/TestStatus";
    import { timestampToISODate } from "../Common/DateUtils";
    import SortHeader from "./SortHeader.svelte";
    import { duration, usd } from "./format";
    import { createSort } from "./sort.svelte";
    import type { TopRun } from "./types";

    interface Props {
        runs: TopRun[];
    }

    let { runs }: Props = $props();

    type Column = "test" | "release" | "backend" | "status" | "start_time" | "duration" | "spend" | "coverage";
    const sort = createSort<Column>("spend");
    const minutes = (run: TopRun) =>
        run.end_time ? new Date(run.end_time).getTime() - new Date(run.start_time).getTime() : null;
    const value = (run: TopRun, by: Column) => {
        if (by === "duration") return minutes(run);
        if (by === "backend") return `${run.backend ?? ""} ${run.region ?? ""}`;
        return run[by];
    };
    const sorted = $derived(sort.apply(runs, value));

    const COVERAGE_BADGE: Record<string, string> = {
        complete: "text-bg-success",
        partial: "text-bg-warning",
        none: "text-bg-secondary",
    };
    const COVERAGE_LABEL: Record<string, string> = { complete: "Complete", partial: "Partial", none: "No data" };

    const runLink = (run: TopRun): string | null =>
        run.build_number === null ? null : `/test/${run.build_id}/${run.build_number}`;
    const statusClass = (status: string): string =>
        (StatusBadgeCSSClassMap as Record<string, string>)[status] ?? "text-bg-secondary";
</script>

<div class="panel rounded p-2 p-md-3 bg-white">
    <h2 class="h6 mb-0">Top runs by cost</h2>
    {#if runs.length === 0}
        <div class="text-body-secondary py-4">No priced run in this range.</div>
    {:else}
        <div class="table-responsive rounded overflow-hidden mt-2">
            <table class="table table-sm table-hover small mb-0">
                <thead>
                    <tr>
                        <SortHeader {sort} key="test" label="Test" />
                        <SortHeader {sort} key="release" label="Release" />
                        <SortHeader {sort} key="backend" label="Backend" />
                        <SortHeader {sort} key="status" label="Status" />
                        <SortHeader {sort} key="start_time" label="Started" defaultDirection="desc" />
                        <SortHeader {sort} key="duration" label="Duration" align="end" />
                        <SortHeader {sort} key="spend" label="Cost" align="end" />
                        <SortHeader {sort} key="coverage" label="Coverage" />
                    </tr>
                </thead>
                <tbody>
                    {#each sorted as run (run.run_id)}
                        {@const link = runLink(run)}
                        <tr>
                            <td class="text-truncate name-col">
                                {#if link}
                                    <a href={link}>{run.test}</a>
                                {:else}
                                    {run.test}
                                {/if}
                                <span class="text-body-secondary">· {run.group}</span>
                            </td>
                            <td>{run.release}</td>
                            <td>{run.backend ?? "—"}{#if run.region}<span class="text-body-secondary ms-1">{run.region}</span>{/if}</td>
                            <td>
                                <span class="badge {statusClass(run.status)}">{run.status.replaceAll("_", " ")}</span>
                                {#if run.spot_terminated}
                                    <span class="badge text-bg-dark">Spot reclaimed</span>
                                {/if}
                            </td>
                            <td class="text-nowrap">{timestampToISODate(new Date(run.start_time).getTime())}</td>
                            <td class="text-end tabular">{duration(run.start_time, run.end_time)}</td>
                            <td class="text-end tabular fw-semibold">{usd(run.spend)}</td>
                            <td><span class="badge {COVERAGE_BADGE[run.coverage]}">{COVERAGE_LABEL[run.coverage]}</span></td>
                        </tr>
                    {/each}
                </tbody>
            </table>
        </div>
    {/if}
</div>

<style>
    .name-col {
        max-width: 28rem;
    }

    .tabular {
        font-variant-numeric: tabular-nums;
    }
</style>
