<script context="module">
    export const getAssigneesForTest = function (assigneeList, testId, groupId, last_runs) {
        let testAssignees = assigneeList.tests?.[testId] ?? [];
        let groupAssignees = assigneeList.groups?.[groupId] ?? [];
        let allAssignees = [...testAssignees, ...groupAssignees];
        let lastRun = last_runs?.[0];
        if (lastRun?.assignee && allAssignees.findIndex(v => v == lastRun.assignee) == -1)
        {
            return [lastRun.assignee];
        }
        return allAssignees;
    };

    export const shouldFilterOutByUser = function (assigneeList, user, test, group = undefined, tests = undefined, type = "test") {
        if (!user) return false;
        switch (type) {
        case "test":
            return getAssigneesForTest(assigneeList, test.test.id, test.test.group_id, test.last_runs) != user.id;
        case "group":
            return (assigneeList.groups?.[group.id]?.[0] ?? "") != user.id && tests.filter(v => !shouldFilterOutByUser(assigneeList, user, v)).length == 0;
        default:
            return false;
        }
    };

</script>

<script>
    import { createEventDispatcher, onDestroy, onMount } from "svelte";
    import queryString from "query-string";
    import Fa from "svelte-fa";
    import {
        faBug,
        faComment,
        faRefresh,
        faArrowLeft,
        faEllipsisH,
        faCheck,
        faTimes,
        faEyeSlash,
        faQuestion,
    } from "@fortawesome/free-solid-svg-icons";

    import {
        TestInvestigationStatus,
        TestStatus,
    } from "../Common/TestStatus";
    import { apiMethodCall } from "../Common/ApiUtils";
    import { userList } from "../Stores/UserlistSubscriber";
    import AssigneeFilter from "./AssigneeFilter.svelte";
    import TestDashboardGroup from "./TestDashboardGroup.svelte";
    import TestDashboardFlatView from "./TestDashboardFlatView.svelte";
    import FlatViewHelper from "./FlatViewHelper.svelte";
    import GroupedViewHelper from "./GroupedViewHelper.svelte";
    export let dashboardObject;
    export let dashboardObjectType = "release";
    export let widgetId;
    export let clickedTests = {};
    export let productVersion;
    export let settings = {};
    export let stats;
    let statRefreshInterval;
    let statsFetchedOnce = false;
    let hideNotPlanned =  JSON.parse(window.localStorage.getItem(`releaseDashHideNotPlanned-${dashboardObject.id}`)) ?? false;
    let versionsIncludeNoVersion = JSON.parse(window.localStorage.getItem(`releaseDashIncludeNoVersions-${dashboardObject.id}`)) ?? (settings.versionsIncludeNoVersion || true);
    let versionsFilterExtraVersions = JSON.parse(window.localStorage.getItem(`releaseDashFilterExtraVersions-${dashboardObject.id}`)) ?? true;
    let users = {};
    let userFilter;
    $: users = $userList;

    const PANEL_MODES = {
        release: {
            statRoute: () => "/api/v1/release/stats/v2",
            versionRoute: (release) => `/api/v1/release/${release.id}/versions`,
        },
        view: {
            statRoute: () => "/api/v1/views/stats",
            versionRoute: (view) => `/api/v1/views/${view.id}/versions`,
        }
    };

    let assigneeList = {
        groups: {

        },
        tests: {

        }
    };

    const dispatch = createEventDispatcher();

    const loadCollapseState = function() {
        return JSON.parse(window.localStorage.getItem(`releaseDashState-${dashboardObject.id}`)) || {};
    };

    const toggleCollapse = function(collapseId, force = false, forcedState = false) {
        if (force) {
            collapseState[collapseId] = forcedState;
        } else {
            collapseState[collapseId] = !(collapseState[collapseId] || false);
        }
        window.localStorage.setItem(`releaseDashState-${dashboardObject.id}`, JSON.stringify(collapseState));
    };

    const getCollapseState = function(collapseId, collapseState) {
        return collapseState[collapseId] ?? false;
    };

    const toggleAllCollapses = function(state = false) {
        for (let collapseId in stats.groups) {
            toggleCollapse(`collapse-${collapseId}`, true, state);
        }
    };

    const allCollapsed = function(collapseState) {
        for (let collapseId in stats.groups) {
            if (!getCollapseState(`collapse-${collapseId}`, collapseState)) {
                return false;
            }
        }
        return true;
    };

    let collapseState = loadCollapseState();


    const fetchStats = async function (force = false) {
        return dashboardObjectType == "release" ? fetchReleaseStats(force) : fetchViewStats(force);
    };

    const fetchReleaseStats = async function (force = false) {
        if (!document.hasFocus() && statsFetchedOnce) return;
        let params = queryString.stringify({
            release: dashboardObject.name,
            limited: new Number(false),
            force: new Number(true),
            includeNoVersion: new Number(versionsIncludeNoVersion),
            productVersion: productVersion ?? (settings.productVersion || ""),
        });
        let opts = force ? {cache: "reload"} : {};
        let response = await fetch(PANEL_MODES.release.statRoute() + "?" + params, opts);
        let json = await response.json();
        if (json.status != "ok") {
            return false;
        }
        stats = json.response;
        dispatch("statsUpdate", stats);
        statsFetchedOnce = true;

        if (stats.release.perpetual) {
            fetchGroupAssignees(dashboardObject.id);
        } else {
            fetchGroupAssignees(dashboardObject.id);
            Object.values(stats.groups).forEach((groupStat, idx) => {
                setTimeout(() => {
                    fetchTestAssignees(groupStat.group.id);
                }, 25 * idx);
            });
        }
    };

    const fetchViewStats = async function (force = false) {
        if (!document.hasFocus() && statsFetchedOnce) return;
        let params = queryString.stringify({
            viewId: dashboardObject.id,
            limited: new Number(false),
            force: new Number(true),
            widgetId: widgetId,
            includeNoVersion: new Number(versionsIncludeNoVersion),
            productVersion: productVersion ?? "",
        });
        let opts = force ? {cache: "reload"} : {};
        let response = await fetch(PANEL_MODES.view.statRoute() + "?" + params, opts);
        let json = await response.json();
        if (json.status != "ok") {
            return false;
        }
        stats = json.response;
        dispatch("statsUpdate", stats);
        statsFetchedOnce = true;

        Object.values(stats.groups).forEach((groupStat, idx) => {
            setTimeout(() => {
                fetchTestAssignees(groupStat.group.id);
            }, 25 * idx);
        });
    };

    const handleDashboardRefreshClick = function() {
        fetchStats(true);
    };

    const handleQuickSelect = function (e) {
        let tests = e.detail.tests;
        tests.forEach((v) => {
            let group = stats.groups[v.test.group_id];
            dispatch("testClick", {
                name: v.test.name,
                id: v.test.id,
                assignees: [...(assigneeList.tests?.[v.test.id] ?? []), ...(assigneeList.groups?.[group.group.id] ?? [])],
                group: group.group.name,
                status: v.status,
                start_time: v.start_time,
                last_runs: v.last_runs,
                build_system_id: v.test.build_system_id,
            });
        });
    };

    /**
     * @param {Object} stats
     * @param {(v: Object) => boolean} key
     */
    const quickTestFilter = function(stats, key) {
        let allTests = Object.values(stats.groups).reduce((tests, group) => [...tests, ...Object.values(group.tests)], []);
        let evt = new CustomEvent("quickSelect", { detail: { tests: allTests.filter(key) } });
        handleQuickSelect(evt);
    };

    const fetchVersions = async function() {
        let response = await fetch(PANEL_MODES[dashboardObjectType].versionRoute(dashboardObject));
        if (response.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await response.json();
        if (json.status !== "ok") {
            return Promise.reject(json.exception);
        }

        return json.response;
    };

    const shouldFilterVersion = function (version) {
        if (!stats) return false;
        if (!versionsFilterExtraVersions) return false;
        try {
            const releaseRegex = stats?.release?.valid_version_regex;
            if (!releaseRegex) return false;
            const re = RegExp(releaseRegex).test(version);
            if (re) return false;

            return true;
        } catch (error) {
            console.log("Failure filtering version", error);
        }
    };

    const handleUserFilter = function(event) {
        let user = event.detail;
        userFilter = user;
    };

    const saveCheckboxState = function(name, state) {
        window.localStorage.setItem(name, JSON.stringify(state));
    };

    const handleVersionClick = function(versionString) {
        productVersion = versionString;
        let params = queryString.parse(document.location.search);
        params.productVersion = versionString;
        history.pushState(undefined, "", `?${queryString.stringify(params, { arrayFormat: "bracket" })}`);
        fetchStats();
        dispatch("versionChange", { version: productVersion });
    };

    const handleTestClick = function (testStats, groupStats) {
        dispatch("testClick", {
            name: testStats.test.name,
            id: testStats.test.id,
            assignees: [...(assigneeList.tests?.[testStats.test.id] ?? []), ...(assigneeList.groups?.[groupStats.group.id] ?? [])],
            group: groupStats.group.name,
            status: testStats.status,
            start_time: testStats.start_time,
            last_runs: testStats.last_runs,
            build_system_id: testStats.test.build_system_id,
        });
    };

    const fetchGroupAssignees = async function(releaseId) {
        let params = queryString.stringify({
            releaseId: releaseId,
            version: productVersion || settings.productVersion,
            planId: dashboardObject.plan_id ?? null,
        });
        let result = await apiMethodCall("/api/v1/release/assignees/groups?" + params, undefined, "GET");
        if (result.status === "ok") {
            assigneeList.groups = Object.assign(assigneeList.groups, result.response);
        }
    };

    const fetchTestAssignees = async function(groupId) {
        let params = queryString.stringify({
            groupId: groupId,
            version: productVersion || settings.productVersion,
            planId: dashboardObject.plan_id ?? null,
        });
        let result = await apiMethodCall("/api/v1/release/assignees/tests?" + params, undefined, "GET");
        if (result.status === "ok") {
            assigneeList.tests = Object.assign(assigneeList.tests, result.response);
        }
    };

    const sortedGroups = function (groups) {
        return Object
            .values(groups)
            .sort((lhs, rhs) => {
                let lhsKey = lhs.group.pretty_name || lhs.group.name;
                let rhsKey = rhs.group.pretty_name || rhs.group.name;
                return lhsKey >= rhsKey ? 1 : -1;
            });
    };

    onMount(() => {
        fetchStats();
        let refreshInterval = 300 + 15 + Math.round((Math.random() * 10));
        statRefreshInterval = setInterval(() => {
            fetchStats();
        }, refreshInterval * 1000);
    });

    onDestroy(() => {
        if (statRefreshInterval) {
            clearInterval(statRefreshInterval);
        }
    });

</script>
<div class="rounded bg-light-one shadow-sm p-2">
    <div class="text-end mb-2">
        <button title="Hide not planned tests" class="btn btn-sm btn-outline-dark" on:click={() => {
                hideNotPlanned = !hideNotPlanned;
                saveCheckboxState(`releaseDashHideNotPlanned-${dashboardObject.id}`, hideNotPlanned);
            }}>
            {#if hideNotPlanned}
                Hide not planned tests
            {:else}
                Show not planned tests
            {/if}
        </button>
        <button title="Refresh" class="btn btn-sm btn-outline-dark" on:click={handleDashboardRefreshClick}>
            <Fa icon={faRefresh}/>
        </button>
        {#if stats}
            {#if allCollapsed(collapseState)}
                <button
                    class="btn btn-outline-dark btn-sm"
                    on:click={() => toggleAllCollapses(false)}
                >
                    Expand all groups
                </button>
            {:else}
                <button
                    class="btn btn-outline-dark btn-sm"
                    on:click={() => toggleAllCollapses(true)}
                >
                    Collapse all groups
                </button>
            {/if}
        {/if}
    </div>
    {#if !settings.targetVersion}
        {#await fetchVersions()}
            <div>Loading versions...</div>
        {:then versions}
            <div class="d-inline-flex flex-wrap mb-2 rounded bg-white p-2" style="flex-basis: 10%; row-gap: 0.75em">
                <button
                    class="btn me-2"
                    class:btn-primary={!productVersion}
                    class:btn-light={productVersion}
                    on:click={() => { handleVersionClick(""); }}>All</button>
                <button
                class="btn me-2"
                class:btn-success={versionsIncludeNoVersion}
                class:btn-danger={!versionsIncludeNoVersion}
                on:click={() => {
                    versionsIncludeNoVersion = !versionsIncludeNoVersion;
                    saveCheckboxState(`releaseDashIncludeNoVersions-${dashboardObject.id}`, versionsIncludeNoVersion);
                    handleVersionClick(productVersion);
                }}>{#if versionsIncludeNoVersion}
                    <Fa icon={faCheck}/>
                {:else}
                    <Fa icon={faTimes}/>
                {/if} No version</button>
                {#each versions as version}
                    {#if !shouldFilterVersion(version, versionsFilterExtraVersions)}
                        <button
                        class="btn btn-light me-2"
                        class:btn-primary={productVersion == version}
                        class:btn-light={productVersion != version}
                        on:click={() => { handleVersionClick(version); }}>{version}</button>
                    {/if}
                {/each}
                {#if stats?.release?.valid_version_regex}
                    <button
                        class="btn me-2 flex-grow-1 flex-shrink-0"
                        class:btn-primary={productVersion == "!noVersion"}
                        class:btn-light={productVersion != "!noVersion"}
                        on:click={() => {
                                versionsFilterExtraVersions = !versionsFilterExtraVersions;
                                saveCheckboxState(`releaseDashFilterExtraVersions-${dashboardObject.id}`, versionsFilterExtraVersions);
                            }}
                    >
                    {#if versionsFilterExtraVersions}
                        <Fa icon={faEllipsisH} />
                    {:else}
                        <Fa icon={faArrowLeft} />
                    {/if}
                    </button>
                {/if}
            </div>
            <br>
        {/await}
    {:else}
        <div class="text center text-muted">
            Version pre-selected: {productVersion || settings.productVersion}
        </div>
    {/if}
    {#if stats}
        <div class="d-flex">
            <div class="mb-2 d-inline-flex align-items-start flex-column rounded bg-white">
                <div class="p-2">
                    Quick filters
                </div>
                <div class="p-2">
                    <div class="btn-group" role="group">
                        <button class="btn btn-primary btn-sm" on:click={() => quickTestFilter(stats, (v) => v?.investigation_status == TestInvestigationStatus.NOT_INVESTIGATED && [TestStatus.FAILED, TestStatus.TEST_ERROR].includes(v?.status))}>
                            <Fa color="#fff" icon={faEyeSlash} />
                            Failed and Not Investigated
                        </button>
                        <button class="btn btn-primary btn-sm" on:click={() => quickTestFilter(stats, (v) => v?.investigation_status == TestInvestigationStatus.INVESTIGATED && [TestStatus.FAILED, TestStatus.TEST_ERROR].includes(v?.status) && !v.hasBugReport)}>
                            <Fa color="#fff" icon={faQuestion} />
                            Investigated w/o Issues
                        </button>
                        <button class="btn btn-primary btn-sm" on:click={() => quickTestFilter(stats, (v) => v["hasBugReport"])}>
                            <Fa color="#fff" icon={faBug} />
                            All w/ Issues
                        </button>
                        <button class="btn btn-primary btn-sm" on:click={() => quickTestFilter(stats, (v) => v["hasComments"])}>
                            <Fa color="#fff" icon={faComment} />
                            All w/ Comments
                        </button>
                    </div>
                </div>
            </div>
            <div class="bg-white rounded mx-2 mb-2 w-25">
                <div class="p-2">Filter by assignee</div>
                <div class="p-2"><AssigneeFilter on:selected={handleUserFilter}/></div>

            </div>
        </div>
        <svelte:component this={settings.flatView ? FlatViewHelper : GroupedViewHelper}>
            {#each sortedGroups(stats.groups) as groupStats (groupStats.group.id)}
                <svelte:component
                    this={settings.flatView ? TestDashboardFlatView : TestDashboardGroup}
                    {assigneeList}
                    {groupStats}
                    {stats}
                    {dashboardObjectType}
                    {users}
                    {hideNotPlanned}
                    {userFilter}
                    bind:clickedTests={clickedTests}
                    collapsed={getCollapseState(`collapse-${groupStats.group.id}`, collapseState)}
                    filtered={shouldFilterOutByUser(assigneeList, userFilter, undefined, groupStats, Object.values(groupStats.tests), "group")}
                    on:quickSelect={handleQuickSelect}
                    on:toggleCollapse={(e) => toggleCollapse(e.detail)}
                    on:testClick={e => handleTestClick(e.detail.testStats, e.detail.groupStats)}
                />
            {/each}
        </svelte:component>
    {:else}
        <div class="d-flex align-items-center justify-content-center text-center">
            <div class="spinner-grow"></div>
            <div class="ms-2 text-bold">Loading Test Dashboard...</div>
        </div>
    {/if}
</div>
