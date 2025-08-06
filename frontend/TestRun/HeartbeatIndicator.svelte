<script lang="ts">
    import { run } from 'svelte/legacy';

    import humanizeDuration from "humanize-duration";
    import { onDestroy, onMount } from "svelte";
    import { InProgressStatuses } from "../Common/TestStatus";
    let { testRun } = $props();

    let clockInterval;
    let heartbeatHuman = $state("");
    let currentTime = $state(new Date());

    run(() => {
        heartbeatHuman = humanizeDuration(
            currentTime - testRun?.heartbeat * 1000,
            { round: true }
        );
    });
    let startedAtHuman = $derived(humanizeDuration(
        currentTime - new Date(testRun?.start_time) ,
        { round: true }
    ));

    onMount(() => {
        clockInterval = setInterval(() => {
            currentTime = new Date();
        }, 1000);
    });

    onDestroy(() => {
        if (clockInterval) clearInterval(clockInterval);
    });
</script>

{#if InProgressStatuses.includes(testRun.status)}
<div class="row text-end">
    <div
        class="col d-flex flex-column text-muted text-sm"
    >
        <div>Last heartbeat: {heartbeatHuman} ago</div>
        <div>Started: {startedAtHuman} ago</div>
    </div>
</div>
{/if}

<style>

</style>
