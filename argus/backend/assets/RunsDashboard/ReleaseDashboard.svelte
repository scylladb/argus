<script>
    export let releaseData = {};
    import ChartStats from "./ChartStats.svelte";
    import ReleaseStats from "./ReleaseStats.svelte";
    import ReleaseActivity from "./ReleaseActivity.svelte";
</script>

<div class="container-fluid border rounded mt-1">
    <div class="row p-2">
        <div class="col p-2">
            <h1 class="display-1">{releaseData.release.name}</h1>
        </div>
        <ReleaseStats releaseName={releaseData.release.name} DisplayItem={ChartStats}/>
    </div>
    <div class="row p-2">
        <div class="border rounded col">
            <h2 class="display-4">Release Activity</h2>
            <ReleaseActivity releaseName={releaseData.release.name} />
        </div>
    </div>
</div>