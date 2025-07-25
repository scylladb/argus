<script>
    import Fa from "svelte-fa";
    import { sendMessage } from "../Stores/AlertStore";
    import { faLink } from "@fortawesome/free-solid-svg-icons";
    import { GLOBAL_STATS_KEY, WIDGET_TYPES } from "../Common/ViewTypes";
    import sha1 from "js-sha1";
    export let view;
    export let stats = {};
    export let productVersion;
    export let embedded = false;
    let clickedTests = {};
    let resolvedTests = [];
    const versionDispatch = {
        GLOBAL_STATS_KEY: productVersion,
    };

    console.log(versionDispatch);

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

    const resolveViewTests = async function() {
        if (resolvedTests.length > 0) {
            return resolvedTests;
        }
        try {
            let response = await fetch(`/api/v1/views/${view.id}/resolve/tests`);
            if (response.status !== 200) {
                throw new Error("Non-200 status code returned from API.");
            }
            let json = await response.json();
            if (json.status === "ok") {
                resolvedTests = json.response;
                return resolvedTests;
            } else {
                throw json;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error resolving view tests.\nMessage: ${error.response.arguments[0]}`,
                    "ViewDashboard::resolveViewTests"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during view test resolution.",
                    "ViewDashboard::resolveViewTests"
                );
                console.log(error);
            }
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

    const calculateWidgetStatsKey = function (widget) {
        return sha1((widget.filter ?? []).join(""));
    };

    const filterViewForWidget = async function (widget) {
        let viewCopy = structuredClone(view);
        if (!widget.filter || widget.filter.length === 0) {
            return viewCopy;
        }
        let tests = await resolveViewTests();
        tests = tests.reduce((acc, test) => {
            acc[test.id] = test;
            return acc;
        }, {});
        viewCopy.tests = viewCopy.tests.filter((item) => {
            const test = tests[item.id] ?? {};
            return ["id", "release_id", "group_id"].some((key) => widget.filter.includes(test[key]));
        });
        return viewCopy;
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
                {#await filterViewForWidget(widget)}
                    <span class="spinner-grow spinner-grow-sm"></span> Loading...
                {:then view}
                    <svelte:component
                        this={WIDGET_TYPES[widget.type]?.type ?? WIDGET_TYPES.UNSUPPORTED.type}
                        widgetId={widget.position}
                        dashboardObject={view}
                        dashboardObjectType="view"
                        settings={widget.settings}
                        bind:stats={stats[calculateWidgetStatsKey(widget)]}
                        bind:productVersion={versionDispatch[calculateWidgetStatsKey(widget)]}
                        bind:clickedTests={clickedTests}
                        on:statsUpdate
                        on:testClick={(e) => handleTestClick(e.detail)}
                        on:versionChange
                        on:quickSelect={handleQuickSelect}
                        on:deleteRequest={handleDeleteRequest}
                    />
                {/await}
            </div>
        {:else}
            <div class="alert alert-danger">No widgets defined for view!</div>
        {/each}
    </div>
</div>
