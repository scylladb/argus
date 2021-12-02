<script>
    import { releaseRequests, stats } from "./StatsSubscriber";
    import NumberStats from "./NumberStats.svelte";
    import TestMapStats from "./TestMapStats.svelte";
    export let releaseName = "";
    export let DisplayItem = NumberStats;
    export let TestMapItem = TestMapStats;
    export let showTestMap = false;
    export let showReleaseStats = true;
    export let horizontal = false;
    const releaseStatsDefault = {
        created: 0,
        running: 0,
        passed: 0,
        failed: 0,
        aborted: 0,
        lastStatus: "unknown",
        disabled: true,
        groups: {},
        tests: {},
        total: -1,
    };
    let releaseStats = releaseStatsDefault;

    releaseRequests.update((val) => [...val, releaseName]);
    $: releaseStats = $stats["releases"]?.[releaseName] ?? releaseStatsDefault;
</script>

<div class="d-flex justify-content-center align-items-center" class:flex-column={!horizontal}>
    {#if releaseStats?.total > 0}
        {#if showReleaseStats}
            <div class="w-100">
                <svelte:component this={DisplayItem} stats={releaseStats} />
            </div>
        {/if}
        {#if showTestMap}
            <div>
                <svelte:component this={TestMapItem} stats={releaseStats} on:testClick />
            </div>
        {/if}
    {:else if releaseStats?.total == -1}
        <span class="spinner-border spinner-border-sm" />
    {:else}
        <!-- svelte-ignore empty-block -->
    {/if}
</div>
