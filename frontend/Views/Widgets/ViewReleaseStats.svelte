<script>
    import ReleaseStats from "../../Stats/ReleaseStats.svelte";
    export let settings;
    export let stats;

</script>

<div class="row mb-2">
    <div class="col">
        <ReleaseStats
            horizontal={settings.horizontal}
            displayExtendedStats={settings.displayExtendedStats}
            hiddenStatuses={settings.hiddenStatuses}
            bind:releaseStats={stats}
            on:quickSelect
        />
    </div>
</div>
