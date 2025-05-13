<script>
    import Fa from "svelte-fa";
    import { WIDGET_TYPES } from "../Common/ViewTypes";
    import { sendMessage } from "../Stores/AlertStore";
    import { faLink } from "@fortawesome/free-solid-svg-icons";
    export let view;
    export let stats = undefined;
    export let productVersion;
    export let embedded = false;
    let clickedTests = {};

    const handleTestClick = function (detail) {
        if (detail.start_time == 0) {
            sendMessage("info", `The test "${detail.name}" hasn't been run yet!"`, "ViewDashboard::handleTestClick");
            return;
        }
        let key = detail.id;
        if (!clickedTests[key]) {
            clickedTests[key] = detail;
        } else {
            delete clickedTests[key];
            clickedTests = clickedTests;
        }
    };

    const handleDeleteRequest = function(e) {
        let key = e.detail.id;
        if (clickedTests[key]) {
            delete clickedTests[key];
            clickedTests = clickedTests;
        }
    };

    const handleQuickSelect = function (e) {
        let tests = e.detail.tests;
        tests.forEach((v) => {
            let group = stats.groups[v.test.group_id];
            handleTestClick({
                name: v.test.name,
                id: v.test.id,
                assignees: [],
                group: group.group.name,
                status: v.status,
                start_time: v.start_time,
                last_runs: v.last_runs,
                build_system_id: v.test.build_system_id,
            });
        });
    };

</script>

<div class="rounded bg-white m-2 shadow-sm p-2">
    <div>
        <h4>{view.display_name || view.name}</h4>
        {#if !embedded && view.plan_id}
            <a href="/plan/{view.plan_id}" class="link-secondary link"><Fa icon={faLink}/>Plan</a>
        {/if}
    </div>
    <div class="mb-2">
        {#each view.widget_settings as widget}
            <div class="mb-2">
                <svelte:component
                    this={WIDGET_TYPES[widget.type]?.type ?? WIDGET_TYPES.UNSUPPORTED.type}
                    dashboardObject={view}
                    dashboardObjectType="view"
                    settings={widget.settings}
                    bind:stats={stats}
                    bind:productVersion={productVersion}
                    bind:clickedTests={clickedTests}
                    on:statsUpdate
                    on:testClick={(e) => handleTestClick(e.detail)}
                    on:versionChange
                    on:quickSelect={handleQuickSelect}
                    on:deleteRequest={handleDeleteRequest}
                />
            </div>
        {:else}
            <div class="alert alert-danger">No widgets defined for view!</div>
        {/each}
    </div>
</div>
