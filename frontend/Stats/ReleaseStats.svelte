<script>
    import NumberStats from "./NumberStats.svelte";
    export let DisplayItem = NumberStats;
    export let showTestMap = false;
    export let showReleaseStats = true;
    export let horizontal = false;
    export let hiddenStatuses = [];
    export let displayExtendedStats = false;

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
    export let releaseStats = releaseStatsDefault;

</script>

<div class="d-flex p-1 align-items-center justify-content-center" class:flex-column={!horizontal} class:align-items-center={!horizontal}>
    {#if releaseStats?.total > 0}
        {#if showReleaseStats}
            <div class="w-100 mb-2">
                <svelte:component this={DisplayItem} stats={releaseStats} displayNumber={displayExtendedStats} displayInvestigations={displayExtendedStats} {hiddenStatuses} on:quickSelect/>
            </div>
        {/if}
    {:else if releaseStats?.total == -1}
        <span class="spinner-border spinner-border-sm" />
    {:else}
        <!-- svelte-ignore empty-block -->
    {/if}
</div>
