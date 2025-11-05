<script lang="ts">
    import NumberStats from "./NumberStats.svelte";

    interface Props {
        DisplayItem?: any;
        showTestMap?: boolean;
        showReleaseStats?: boolean;
        horizontal?: boolean;
        hiddenStatuses?: any;
        displayExtendedStats?: boolean;
        releaseStats?: any;
        widgetId?: number;
    }

    let {
        DisplayItem = NumberStats,
        showTestMap = false,
        showReleaseStats = true,
        horizontal = false,
        hiddenStatuses = [],
        displayExtendedStats = false,
        releaseStats,
        widgetId,
    }: Props = $props();

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

</script>

<div class="d-flex p-1 align-items-center justify-content-center" class:flex-column={!horizontal} class:align-items-center={!horizontal}>
    {#if releaseStats?.total > 0}
        {#if showReleaseStats}
            <div class="w-100 mb-2">
                <DisplayItem stats={releaseStats} displayNumber={displayExtendedStats} displayInvestigations={displayExtendedStats} {hiddenStatuses} {widgetId} on:quickSelect/>
            </div>
        {/if}
    {:else if releaseStats?.total == -1}
        <span class="spinner-border spinner-border-sm"></span>
    {:else}
        <!-- svelte-ignore block_empty -->
    {/if}
</div>
