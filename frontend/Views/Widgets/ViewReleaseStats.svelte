<script lang="ts">
    import ReleaseStats from "../../Stats/ReleaseStats.svelte";
    let { widgetId, settings, stats = $bindable() } = $props();

</script>

<div class="row mb-2">
    <div class="col">
        <ReleaseStats
            widgetId={widgetId}
            horizontal={settings.horizontal}
            displayExtendedStats={settings.displayExtendedStats}
            hiddenStatuses={settings.hiddenStatuses}
            bind:releaseStats={stats}
            on:quickSelect
        />
    </div>
</div>
