<script>
    import { releaseRequests, stats } from "./StatsSubscriber";
    import NumberStats from "./NumberStats.svelte";
    export let releaseName = "";
    export let DisplayItem = NumberStats;
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

    releaseRequests.update(val => [...val, releaseName]);
    $: releaseStats = $stats["releases"]?.[releaseName] ?? releaseStatsDefault;

</script>

<div>
{#if (releaseStats?.total) > 0}
    <svelte:component this={DisplayItem} stats={releaseStats} />
{:else if releaseStats?.total == -1}
    <span class="spinner-border spinner-border-sm"></span>
{:else}
    <!-- svelte-ignore empty-block -->
{/if}
</div>
