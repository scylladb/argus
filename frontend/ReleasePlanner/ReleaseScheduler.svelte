<script lang="ts">
    import { run } from 'svelte/legacy';

    import { onMount } from "svelte";
    import Fa from "svelte-fa";
    import { faCalendar, faDashboard} from "@fortawesome/free-solid-svg-icons";
    import ReleasePlanTable from "./ReleasePlanTable.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    import { sendMessage } from "../Stores/AlertStore";
    import ReleasePlanEditor from "./ReleasePlanEditor.svelte";

    let { releaseData = {}, schedules = $bindable([]) } = $props();
    let users = $state({});
    run(() => {
        users = $userList;
    });
    let selectedTests = $state([]);
    let clickedTests = $state({});
    let plannerData = $state({});
    let editorMode = "create";
    let selectedAssignee = $state();

    let releasePlanEditorComponent = $state();

    const fetchPlannerData = async function () {
        try {
            let params = new URLSearchParams({
                releaseId: releaseData.release.id,
            }).toString();
            let apiResponse = await fetch("/api/v1/release/planner/data?" + params, {
                method: "GET",
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                plannerData = apiJson.response ?? {};
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to fetch planner data.\nMessage: ${error.response.arguments[0]}`,
                    "ReleasePlanner::fetchPlannerData"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during planner data fetch",
                    "ReleasePlanner::fetchPlannerData"
                );
            }
        }
    };

    const fetchSchedules = async function () {
        try {
            let params = new URLSearchParams({
                releaseId: releaseData.release.id,
            });

            let apiResponse = await fetch("/api/v1/release/schedules?" + params, {
                method: "GET",
            });

            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                schedules = apiJson.response?.schedules ?? [];
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to fetch schedules.\nMessage: ${error.response.arguments[0]}`,
                    "ReleasePlanner::fetchSchedules"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during schedule fetch",
                    "ReleasePlanner::fetchSchedules"
                );
            }
        }
    };

    const handleTestClick = function (test) {
        if (selectedTests.findIndex((t) => t.id == test.id) == -1) {
            selectedTests.push(test);
            selectedTests = selectedTests;
            clickedTests[test.id] = true;
            clickedTests = clickedTests;
        } else {
            clickedTests[test.id] = false;
            clickedTests = clickedTests;
            selectedTests = selectedTests.filter((t) => t.id != test.id);
        }
    };

    const handleScheduledTestClick = function(e) {
        let schedule = e.detail.schedule;
        let test = e.detail.test;
        let testEntities = plannerData.tests.filter(v => schedule.tests.includes(v.id));
        if (releasePlanEditorComponent.getCurrentMode() != "edit" || releasePlanEditorComponent.getCurrentScheduleId() != schedule.id) {
            releasePlanEditorComponent.enterEditMode(schedule);
            selectedTests = testEntities;
            selectedAssignee = users[schedule.assignees[0]];
            clickedTests = {};
            selectedTests.forEach(v => clickedTests[v.id] = true);
        } else {
            handleTestClick(test);
        }
    };

    const handleSelectAll = function(e) {
        let testsToIgnore = schedules.map(v => v.tests).reduce((acc, val) => [...acc, ...val], []);
        let selectedTests = e.detail.tests.filter(v => !testsToIgnore.includes(v.id));
        selectedTests.forEach(v => handleTestClick(v));
    };

    onMount(() => {
        fetchSchedules();
        fetchPlannerData();
    });
</script>

<div class="container-fluid border rounded bg-white my-3 min-vh-100 shadow-sm">
    <div class="row">
        <h1 class="display-1">{releaseData.release.name}</h1>
        <div class="btn-group mb-2">
            <a class="btn btn-outline-primary" href="/release/{releaseData.release.name}/duty"
                ><Fa icon={faCalendar} /> Group Planner</a
            >
            <a class="btn btn-outline-primary" href="/dashboard/{releaseData.release.name}"
                ><Fa icon={faDashboard} /> Release Dashboard</a
            >
        </div>
    </div>
    <div class="row">
        <div class="col-xs-2 col-sm-6 col-md-7">
            {#if Object.values(users).length > 0 && plannerData.release}
                <ReleasePlanTable
                    {releaseData}
                    {users}
                    {schedules}
                    {plannerData}
                    bind:clickedTests
                    on:testClick={(e) => handleTestClick(e.detail.test)}
                    on:selectAllClick={handleSelectAll}
                    on:scheduledTestClick={handleScheduledTestClick}
                />
            {/if}
        </div>
        <div class="col-xs-10 col-sm-6 col-md-5">
            {#if Object.values(users).length > 0 && plannerData.release}
                <ReleasePlanEditor
                    bind:this={releasePlanEditorComponent}
                    {plannerData}
                    {users}
                    {releaseData}
                    mode={editorMode}
                    bind:selectedTests
                    bind:clickedTests
                    bind:selectedAssignee
                    on:fetchSchedules={fetchSchedules}
                    on:fetchPlannerData={fetchPlannerData}
                />
            {/if}
        </div>
    </div>
</div>

<style>

</style>
