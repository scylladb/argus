<script lang="ts">
    import { sendMessage } from "../Stores/AlertStore";
    import { loadExplorer } from "./api";
    import Coverage from "./Coverage.svelte";
    import FilterBar from "./FilterBar.svelte";
    import Inset from "./Inset.svelte";
    import ReleaseBreakdown from "./ReleaseBreakdown.svelte";
    import SpendOverTime from "./SpendOverTime.svelte";
    import SpotTerminations from "./SpotTerminations.svelte";
    import StatTiles from "./StatTiles.svelte";
    import TierSplit from "./TierSplit.svelte";
    import TopRuns from "./TopRuns.svelte";
    import { fitRange, overlaps, parseFilters, serializeFilters } from "./filters";
    import type { ExplorerFilters, ExplorerResponse } from "./types";

    interface Props {
        initialSearch?: string;
    }

    let { initialSearch = typeof location === "undefined" ? "" : location.search }: Props = $props();

    // svelte-ignore state_referenced_locally
    let filters: ExplorerFilters = $state(parseFilters(initialSearch));
    let data: ExplorerResponse | undefined = $state();
    let loading = $state(true);
    let error = $state("");
    let requestId = 0;
    let fittedTo = "";

    const windowDays = $derived.by(() => {
        if (!data) return 0;
        return Math.round((new Date(data.window.to).getTime() - new Date(data.window.from).getTime()) / 86_400_000);
    });
    const backends = $derived(data ? Object.keys(data.series.backends) : []);

    const load = async (snapshot: ExplorerFilters, id: number) => {
        loading = true;
        try {
            const result = await loadExplorer(snapshot);
            if (id !== requestId) return;
            data = result;
            error = "";
            const selection = snapshot.releaseNames.join("|");
            if (result.span && result.tiles.runs === 0 && !overlaps(snapshot, result.span) && fittedTo !== selection) {
                fittedTo = selection;
                Object.assign(filters, fitRange(result.span));
            }
        } catch (e) {
            if (id !== requestId) return;
            error = e instanceof Error ? e.message : "Could not load the cost figures.";
            sendMessage("error", error, "CostExplorer::load");
        } finally {
            if (id === requestId) loading = false;
        }
    };

    $effect(() => {
        const snapshot = $state.snapshot(filters);
        const id = ++requestId;
        load(snapshot, id);
        if (typeof history !== "undefined" && typeof location !== "undefined") {
            history.replaceState(null, "", `${location.pathname}?${serializeFilters(snapshot)}`);
        }
    });
</script>

<div class="border rounded bg-white shadow-sm p-2 p-md-3 d-flex flex-column gap-2 gap-md-3">
    <div class="d-flex justify-content-between align-items-end flex-wrap gap-2">
        <div>
            <h1 class="h4 mb-0">Cost Explorer</h1>
        </div>
        {#if loading}
            <div class="text-body-secondary small"><span class="spinner-border spinner-border-sm"></span> Loading…</div>
        {/if}
    </div>

    <FilterBar bind:filters {backends} span={data?.span ?? null} />

    {#if error && !data}
        <div class="alert alert-danger mb-0">{error}</div>
    {:else if data}
        <Inset class="d-flex flex-column gap-1 gap-md-2">
            <StatTiles tiles={data.tiles} {windowDays} />
            <div class="row g-1 g-md-2">
                <div class="col-12 col-xl-8">
                    <SpendOverTime series={data.series} granularity={data.window.granularity} />
                </div>
                <div class="col-12 col-xl-4">
                    <Coverage coverage={data.coverage} />
                </div>
            </div>
            <div class="row g-1 g-md-2">
                <div class="col-12 col-xl-8">
                    <ReleaseBreakdown releases={data.releases} breakdown={data.window.breakdown} />
                </div>
                <div class="col-12 col-xl-4 d-flex flex-column gap-1 gap-md-2">
                    <TierSplit tiers={data.tiers} />
                    <SpotTerminations terminations={data.spot_terminations} />
                </div>
            </div>
            <TopRuns runs={data.top_runs} />
        </Inset>
    {/if}
</div>
