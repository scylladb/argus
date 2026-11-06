<script lang="ts">
    import { onMount } from "svelte";
    import Fa from "svelte-fa";
    import { faChevronDown, faChevronRight } from "@fortawesome/free-solid-svg-icons";
    import { fetchJson } from "../../../Common/ApiUtils";
    import { sendMessage } from "../../../Stores/AlertStore";
    import FamilySummary from "./FamilySummary.svelte";
    import SummaryBar from "./SummaryBar.svelte";
    import { updatedAgo } from "./summaryUtils";
    import type { ReleaseSummaryResponse, SummaryTest } from "./types";

    interface Props {
        dashboardObject: { id: string };
        dashboardObjectType?: "view" | "release";
        collapsible?: boolean;
        onTestClick?: (test: SummaryTest, event: MouseEvent) => void;
    }

    let { dashboardObject, dashboardObjectType = "view", collapsible = false, onTestClick }: Props = $props();

    const HEADER_FAMILIES = 3;

    let releases: ReleaseSummaryResponse[] | undefined = $state();
    let error = $state("");
    let expanded = $state(false);

    const isOpen = $derived(!collapsible || expanded);
    const headerFamilies = $derived((releases ?? []).flatMap((release) => release.families).slice(0, HEADER_FAMILIES));

    const REFRESH_MS = 3000;
    const REFRESH_TRIES = 5;

    let refreshes = 0;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const refreshing = $derived((releases ?? []).some((release) => release.stale) && refreshes < REFRESH_TRIES);

    const load = async () => {
        try {
            if (dashboardObjectType === "release") {
                releases = [await fetchJson(`/api/v1/release/${dashboardObject.id}/version_summary`)];
            } else {
                const response: { releases: ReleaseSummaryResponse[] } = await fetchJson(
                    `/api/v1/views/widgets/release_summary?view_id=${dashboardObject.id}`,
                );
                releases = response.releases;
            }
            if (releases.some((release) => release.stale) && refreshes < REFRESH_TRIES) {
                refreshes += 1;
                refreshTimer = setTimeout(load, REFRESH_MS);
            }
        } catch (e) {
            error = e instanceof Error ? e.message : "Could not load the release summary.";
            sendMessage("error", error, "ReleaseSummary::load");
        }
    };

    onMount(() => {
        load();
        return () => clearTimeout(refreshTimer);
    });
</script>

{#snippet body()}
    {#if error}
        <div class="alert alert-danger mb-0">{error}</div>
    {:else if !releases}
        <div class="text-body-secondary p-2">
            <span class="spinner-border spinner-border-sm"></span> Loading the release summary…
        </div>
    {:else}
        {#each releases as release (release.release_id)}
            <div class="d-flex flex-wrap align-items-baseline gap-2 mb-2">
                {#if dashboardObjectType === "view"}
                    <h3 class="h6 mb-0">{release.release_name}</h3>
                {/if}
                {#if release.generated_at}
                    <span class="small text-body-secondary ms-auto" title={release.generated_at}
                        >Updated {updatedAgo(release.generated_at)}</span
                    >
                {/if}
            </div>
            {#if release.stale && refreshing}
                <div class="small text-body-secondary mb-2">
                    <span class="spinner-border spinner-border-sm"></span> Refreshing; showing the figures stored
                    {updatedAgo(release.generated_at)}.
                </div>
            {:else if release.stale}
                <div class="alert alert-warning py-1 px-2 small">
                    The summary could not be refreshed. It shows the figures stored {updatedAgo(release.generated_at)}.
                </div>
            {/if}
            {#if release.families.length === 0}
                <div class="text-body-secondary p-2">No tested or planned versions yet.</div>
            {:else}
                <div class="rounded bg-light-one shadow-sm p-2 d-flex flex-column gap-2 mb-2">
                    {#each release.families as family, index (family.family)}
                        <FamilySummary {family} initiallyOpen={index === 0} {onTestClick} />
                    {/each}
                </div>
            {/if}
        {/each}
    {/if}
{/snippet}

{#if collapsible}
    <div class="accordion">
        <div class="accordion-item">
            <h2 class="accordion-header">
                <button
                    type="button"
                    class="accordion-button gap-3 flex-wrap"
                    class:collapsed={!expanded}
                    aria-expanded={expanded}
                    onclick={() => (expanded = !expanded)}
                >
                    <span>Release summary</span>
                    {#each headerFamilies as family (family.family)}
                        <span class="d-inline-flex align-items-center gap-1 small">
                            <span class="fw-semibold header-family">{family.family}</span>
                            <SummaryBar counts={family.rollup.counts} label="Results of {family.family}" compact />
                        </span>
                    {/each}
                </button>
            </h2>
            {#if isOpen}
                <div class="accordion-body">
                    {@render body()}
                </div>
            {/if}
        </div>
    </div>
{:else}
    <div class="mb-2">
        <h2 class="h5 mb-2">Release summary</h2>
        {@render body()}
    </div>
{/if}

<style>
    .header-family {
        display: inline-block;
        min-width: 5.5rem;
        text-align: right;
    }
</style>
