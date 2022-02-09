<script>
    import { releaseRequests, stats } from "../Stores/StatsSubscriber";
    import NumberStats from "./NumberStats.svelte";
    import TestMapStats from "./TestMapStats.svelte";
    import { createEventDispatcher } from "svelte";
    export let releaseName = "";
    export let DisplayItem = NumberStats;
    export let TestMapItem = TestMapStats;
    export let showTestMap = false;
    export let showReleaseStats = true;
    export let horizontal = false;
    export let clickedTests = {};
    const dispatch = createEventDispatcher();
    const releaseStatsDefault = {
        created: 0,
        running: 0,
        passed: 0,
        failed: 0,
        aborted: 0,
        lastStatus: "unknown",
        disabled: true,
        limited: !showTestMap,
        groups: {},
        tests: {},
        total: -1,
    };
    let releaseStats = releaseStatsDefault;
    releaseRequests.update((val) => [...val, releaseName]);
    $: releaseStats = $stats["releases"]?.[releaseName] ?? releaseStatsDefault;
    $: dispatch("statsUpdate", { stats: releaseStats });
</script>

<div class="d-flex justify-content-center" class:flex-column={!horizontal} class:align-items-center={!horizontal}>
    {#if releaseStats?.total > 0}
        {#if showReleaseStats}
            <div class="w-100">
                <svelte:component this={DisplayItem} stats={releaseStats} />
            </div>
        {/if}
        {#if showTestMap}
            <div>
                <svelte:component this={TestMapItem} stats={releaseStats} {releaseName} bind:clickedTests={clickedTests} on:testClick />
            </div>
        {/if}
    {:else if releaseStats?.total == -1}
        <span class="spinner-border spinner-border-sm" />
    {:else}
        <!-- svelte-ignore empty-block -->
    {/if}
</div>
