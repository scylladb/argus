<script>
    import humanizeDuration from "humanize-duration";
    import { onDestroy, onMount } from "svelte";
    import { InProgressStatuses } from "../Common/TestStatus";
    export let testRun;

    let clockInterval;
    let heartbeatHuman = "";
    let currentTime = new Date();

    $: heartbeatHuman = humanizeDuration(
        currentTime - testRun?.heartbeat * 1000,
        { round: true }
    );
    $: startedAtHuman = humanizeDuration(
        currentTime - new Date(testRun?.start_time) ,
        { round: true }
    );

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
