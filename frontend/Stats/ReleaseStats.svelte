<script>
    import NumberStats from "./NumberStats.svelte";
    import { createEventDispatcher, onDestroy, onMount } from "svelte";
    export let releaseName = "";
    export let DisplayItem = NumberStats;
    export let showTestMap = false;
    export let showReleaseStats = true;
    export let horizontal = false;
    const dispatch = createEventDispatcher();
    const fetchStats = async function () {
        let params = new URLSearchParams({
            release: releaseName,
            limited: new Number(false),
            force: new Number(false),
        });
        let response = await fetch("/api/v1/release/stats/v2?" + params);
        let json = await response.json();
        if (json.status != "ok") {
            return false;
        }
        releaseStats = json.response;
        dispatch("statsUpdate", { stats: releaseStats });
    };

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

    let statRefreshInterval;
    let releaseStats = releaseStatsDefault;

    onMount(() => {
        fetchStats();

        statRefreshInterval = setInterval(() => {
            fetchStats();
        }, 30 * 1000);
    });

    onDestroy(() => {
        if (statRefreshInterval) {
            clearInterval(statRefreshInterval);
        }
    });

</script>

<div class="d-flex p-1 align-items-center justify-content-center" class:flex-column={!horizontal} class:align-items-center={!horizontal}>
    {#if releaseStats?.total > 0}
        {#if showReleaseStats}
            <div class="w-100 mb-2">
                <svelte:component this={DisplayItem} stats={releaseStats} />
            </div>
        {/if}
    {:else if releaseStats?.total == -1}
        <span class="spinner-border spinner-border-sm" />
    {:else}
        <!-- svelte-ignore empty-block -->
    {/if}
</div>
