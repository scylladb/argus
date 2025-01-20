<script>
    export let dashboardObject;
    export let dashboardObjectType;
    export let stats;
    export let settings;
    export let productVersion;
    export let clickedTests;
    export let widgetId;

    import TestDashboard from "../../ReleaseDashboard/TestDashboard.svelte";
    import TestPopoutSelector from "../../ReleaseDashboard/TestPopoutSelector.svelte";

</script>
<div class="row mb-2">
    <div class="col-xs-2 col-sm-6 col-md-7">
        <TestDashboard
            dashboardObject={dashboardObject}
            {dashboardObjectType}
            {settings}
            {widgetId}
            bind:productVersion={productVersion}
            bind:stats={stats}
            bind:clickedTests={clickedTests}
            on:testClick
            on:versionChange
            on:statsUpdate
        />
    </div>
    <div class="col-xs-10 col-sm-6 col-md-5">
        <TestPopoutSelector
            bind:tests={clickedTests}
            on:deleteRequest
        />
    </div>
</div>
