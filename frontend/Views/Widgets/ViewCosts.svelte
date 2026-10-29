<script lang="ts">
    import { onMount } from "svelte";
    import { fetchJson } from "../../Common/ApiUtils";
    import { sendMessage } from "../../Stores/AlertStore";
    import Inset from "../../CostExplorer/Inset.svelte";
    import SpendOverTime from "../../CostExplorer/SpendOverTime.svelte";
    import StatTiles from "../../CostExplorer/StatTiles.svelte";
    import { presetRange } from "../../CostExplorer/filters";
    import type { ExplorerResponse } from "../../CostExplorer/types";

    interface Props {
        dashboardObject: { id: string };
        settings: { days?: number };
    }

    let { dashboardObject, settings }: Props = $props();

    const days = $derived(Number(settings?.days) > 0 ? Math.min(Number(settings.days), 366) : 30);
    let data: ExplorerResponse | undefined = $state();
    let error = $state("");
    const windowDays = $derived(
        data ? Math.round((new Date(data.window.to).getTime() - new Date(data.window.from).getTime()) / 86_400_000) : days
    );

    const pageLink = $derived.by(() => {
        const range = presetRange(days);
        const params = new URLSearchParams({ viewId: dashboardObject.id, from: range.from, to: range.to });
        return `/costs?${params.toString()}`;
    });

    onMount(async () => {
        try {
            data = await fetchJson(`/api/v1/views/widgets/costs?view_id=${dashboardObject.id}&days=${days}`);
        } catch (e) {
            error = e instanceof Error ? e.message : "Could not load the cost figures.";
            sendMessage("error", error, "ViewCosts::load");
        }
    });
</script>

<div class="mb-2">
    <div class="d-flex justify-content-between align-items-baseline flex-wrap gap-2 mb-2">
        <div>
            <h2 class="h5 mb-0">Costs</h2>
            <div class="small text-body-secondary">Total spend of this view's runs</div>
        </div>
        <a href={pageLink} class="btn btn-sm btn-outline-primary">Open in the Cost Explorer</a>
    </div>
    {#if error}
        <div class="alert alert-danger mb-0">{error}</div>
    {:else if !data}
        <div class="text-body-secondary p-2"><span class="spinner-border spinner-border-sm"></span> Loading costs…</div>
    {:else}
        <Inset class="d-flex flex-column gap-1 gap-md-2">
            <StatTiles tiles={data.tiles} {windowDays} />
            <SpendOverTime series={data.series} granularity={data.window.granularity} />
        </Inset>
    {/if}
</div>
