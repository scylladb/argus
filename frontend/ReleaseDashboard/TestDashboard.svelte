<script module>
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

<script lang="ts">
    import { run } from 'svelte/legacy';

    import { createEventDispatcher, onDestroy, onMount } from "svelte";
    import queryString from "query-string";
    import sha1 from "js-sha1";
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
        faCheckSquare,
        faSquare,
    } from "@fortawesome/free-solid-svg-icons";

    import {
        InvestigationStatusIcon,
        StatusBackgroundCSSClassMap,
        StatusButtonCSSClassMap,
        TestInvestigationStatus,
        TestStatus,

        TestStatusFilterDefaultState

    } from "../Common/TestStatus";
    import { apiMethodCall } from "../Common/ApiUtils";
    import { userList } from "../Stores/UserlistSubscriber";
    import AssigneeFilter from "./AssigneeFilter.svelte";
    import TestDashboardGroup from "./TestDashboardGroup.svelte";
    import TestDashboardFlatView from "./TestDashboardFlatView.svelte";
    import FlatViewHelper from "./FlatViewHelper.svelte";
    import GroupedViewHelper from "./GroupedViewHelper.svelte";
    import Select from "svelte-select";
    import { Collapse } from "bootstrap";
    import { titleCase } from "../Common/TextUtils";
    interface Props {
        dashboardObject: any;
        dashboardObjectType?: string;
        widgetId: any;
        clickedTests?: any;
        productVersion: any;
        settings?: any;
        stats: any;
    }

    let {
        dashboardObject,
        dashboardObjectType = "release",
        widgetId,
        clickedTests = $bindable({}),
        productVersion = $bindable(),
        settings = {},
        stats = $bindable()
    }: Props = $props();
    let imageId = $state(null);
    let dashboardFilterShow = false;
    let statRefreshInterval;
    let statsFetchedOnce = false;
    let versionsIncludeNoVersion = $state(JSON.parse(window.localStorage.getItem(`releaseDashIncludeNoVersions-${dashboardObject.id}`)) ?? (settings.versionsIncludeNoVersion || true));
    let versionsFilterExtraVersions = $state(JSON.parse(window.localStorage.getItem(`releaseDashFilterExtraVersions-${dashboardObject.id}`)) ?? true);
    let users = $state({});
    run(() => {
        users = $userList;
    });

    const PANEL_MODES = {
        release: {
            statRoute: () => "/api/v1/release/stats/v2",
            versionRoute: (release) => `/api/v1/release/${release.id}/versions`,
            imagesRoute: (release) => `/api/v1/release/${release.id}/images`,
        },
        view: {
            statRoute: () => "/api/v1/views/stats",
            versionRoute: (view) => `/api/v1/views/${view.id}/versions`,
            imagesRoute: (view) => `/api/v1/views/${view.id}/images`,
        }
    };

    const FILTER_STACK = $state({
        user: {
            f: function (test) {
                if (!this.state) return true;
                const assignees = getAssigneesForTest(assigneeList, test.test.id, test.test.group_id, test.last_runs);
                return assignees.includes(this.state?.id);
            },
            op: (a, b) => a && b,
            state: undefined,
        },
        status: {
            /**
             * @param test {{status: string}}
             */
            f: function (test) {
                return this.state[test.status];
            },
            op: (a, b) => a && b,
            state: Object.assign({}, TestStatusFilterDefaultState),
        },
        backend: {
            f: function(test) {
                const lastRun = test.last_runs?.[0];
                if (!this.state) return true;
                if (!lastRun) return false;
                return (lastRun?.setup?.backend ?? "None") == this.state;
            },
            op: (a, b) => a && b,
            state: undefined,
            options: [],
            populate: function (stats) {
                let backends = Object
                    .values(stats.groups)
                    .flatMap(g => Object.values(g.tests))
                    .map(test => (test.last_runs?.[0]?.setup?.backend) || "None")
                    .sort();
                return Array.from(new Set(backends));
            },
        },
    });


    const generateCollapseKey = function(dashboardObject, dashboardObjectType) {
        if (dashboardObjectType == "release") {
            return dashboardObject.id;
        } else {
            return sha1(dashboardObject.tests.join("_#_"));
        }
    };

    const populateFilterStackOptions = function(stats) {
        Object.values(FILTER_STACK).forEach(filter => {
            if (filter.populate) filter.options = filter.populate(stats);
        });
    };

    const loadedState = JSON.parse(window.localStorage.getItem(`testDashFilterState-${dashboardObject.id}`));
    if (loadedState) {
        Object.entries(loadedState).forEach(([key, state]) => {
            FILTER_STACK[key].state = state;
        });
    }

    run(() => {
        let state = Object.entries(FILTER_STACK).reduce((acc, [key, filter]) => {
            acc[key] = filter.state;
            return acc;
        }, {});
        const serializedState = JSON.stringify(state);
        window.localStorage.setItem(`testDashFilterState-${dashboardObject.id}`, serializedState);
    });

    let assigneeList = $state({
        groups: {

        },
        tests: {

        }
    });

    const doFilters = function(test, stack) {
        let filterState = Object.values(stack).map(filter => {
            return [filter.f(test), filter.op];
        });

        let finalResult = true;
        while (filterState.length > 0) {
            let [filterResult, filterOp] = filterState.shift();
            finalResult = filterOp(finalResult, filterResult);
        }

        return finalResult;
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

    let collapseState = $state(loadCollapseState());


    const fetchStats = async function (force = false) {
        return dashboardObjectType == "release" ? fetchReleaseStats(force) : fetchViewStats(force);
    };

    const fetchReleaseStats = async function (force = false) {
        if (!document.hasFocus() && statsFetchedOnce) return;
        let params = queryString.stringify({
            release: dashboardObject.name,
            limited: new Number(false),
            force: new Number(true),
            imageId: imageId,
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
        populateFilterStackOptions(stats);
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
            imageId: imageId,
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
        let tests = e.detail.tests ?? [];
        const detailGroups = e.detail.groups ?? {};
        tests.forEach((v) => {
            const groupStats = detailGroups[v.test.group_id] ?? stats?.groups?.[v.test.group_id];
            const groupId = groupStats?.group?.id ?? v.test.group_id;
            const groupAssignees = groupId ? assigneeList.groups?.[groupId] ?? [] : [];
            dispatch("testClick", {
                name: v.test.name,
                id: v.test.id,
                assignees: [...(assigneeList.tests?.[v.test.id] ?? []), ...groupAssignees],
                group: groupStats?.group?.name ?? v.test.group?.name ?? groupId ?? "Unknown group",
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
        let evt = new CustomEvent("quickSelect", { detail: { tests: allTests.filter(key), groups: stats.groups } });
        handleQuickSelect(evt);
    };

    const fetchVersions = async function() {
        const extractShortVersions = function (version) {
            const VERSION_RE = /^(?<short>((?<oss>\d)|(?<ent>\d{4}))\.(\d*)\.(\d*)((~|\.)rc\d|~dev|\.dev)?)((-|\.)(?<build>(0\.)?(?<date>[0-9]{8,8})\.(?<commit>\w+).*))?$/;
            let match = VERSION_RE.exec(version);
            if (!match) return null;
            const isEnterprise = !!match.groups.ent;
            return [match.groups.short, isEnterprise];
        };
        let response = await fetch(PANEL_MODES[dashboardObjectType].versionRoute(dashboardObject));
        if (response.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await response.json();
        if (json.status !== "ok") {
            return Promise.reject(json.exception);
        }
        const unrecognizedVersions = [];
        const uniqueShortVersions = json.response
            .map(v => extractShortVersions(v) || (unrecognizedVersions.push(v) && false))
            .filter(v => v);

        const enterpriseVersions = uniqueShortVersions
            .filter(([_, isEnterprise]) => isEnterprise)
            .map(([version]) => version)
            .filter((version, idx, src) => src.indexOf(version) === idx)
            .sort()
            .reverse();
        const ossVersions = uniqueShortVersions
            .filter(([_, isEnterprise]) => !isEnterprise)
            .map(([version]) => version)
            .filter((version, idx, src) => src.indexOf(version) === idx)
            .sort()
            .reverse();

        return [...enterpriseVersions, ...ossVersions, ...unrecognizedVersions];
    };

    const fetchImages = async function() {
        let response = await fetch(PANEL_MODES[dashboardObjectType].imagesRoute(dashboardObject));
        if (response.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await response.json();
        if (json.status !== "ok") {
            return Promise.reject(json.exception);
        }

        return json.response.map(v => ({ label: v, value : v}));
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

    const hideEmptyGroup = function (groupStats) {
        const shouldBeHidden = Object.values(groupStats.tests).map((test) => doFilters(test, FILTER_STACK)).filter(t => t);
        return shouldBeHidden.length == 0;
    };

    const handleUserFilter = function(event) {
        let user = event.detail;
        FILTER_STACK.user.state = user;
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

    const loadOptionValue = function(stack, key) {
        if (!stack[key] || !stack[key].state) return null;
        return {
            label: stack[key].state,
            value: stack[key].state
        };
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
        <button title="Refresh" class="btn btn-sm btn-outline-dark" onclick={handleDashboardRefreshClick}>
            <Fa icon={faRefresh}/>
        </button>
        {#if stats}
            {#if allCollapsed(collapseState)}
                <button
                    class="btn btn-outline-dark btn-sm"
                    onclick={() => toggleAllCollapses(false)}
                >
                    Expand all groups
                </button>
            {:else}
                <button
                    class="btn btn-outline-dark btn-sm"
                    onclick={() => toggleAllCollapses(true)}
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
                    onclick={() => { handleVersionClick(""); }}>All</button>
                <button
                class="btn me-2"
                class:btn-success={versionsIncludeNoVersion}
                class:btn-danger={!versionsIncludeNoVersion}
                onclick={() => {
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
                        onclick={() => { handleVersionClick(version); }}>{version}</button>
                    {/if}
                {/each}
                {#if stats?.release?.valid_version_regex}
                    <button
                        class="btn me-2 flex-grow-1 flex-shrink-0"
                        class:btn-primary={productVersion == "!noVersion"}
                        class:btn-light={productVersion != "!noVersion"}
                        onclick={() => {
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
                        <button class="btn btn-primary btn-sm" onclick={() => quickTestFilter(stats, (v) => v?.investigation_status == TestInvestigationStatus.NOT_INVESTIGATED && [TestStatus.FAILED, TestStatus.TEST_ERROR].includes(v?.status))}>
                            <Fa color="#fff" icon={faEyeSlash} />
                            Failed and Not Investigated
                        </button>
                        <button class="btn btn-primary btn-sm" onclick={() => quickTestFilter(stats, (v) => v?.investigation_status == TestInvestigationStatus.INVESTIGATED && [TestStatus.FAILED, TestStatus.TEST_ERROR].includes(v?.status) && !v.hasBugReport)}>
                            <Fa color="#fff" icon={faQuestion} />
                            Investigated w/o Issues
                        </button>
                        <button class="btn btn-primary btn-sm" onclick={() => quickTestFilter(stats, (v) => v["hasBugReport"])}>
                            <Fa color="#fff" icon={faBug} />
                            All w/ Issues
                        </button>
                        <button class="btn btn-primary btn-sm" onclick={() => quickTestFilter(stats, (v) => v["hasComments"])}>
                            <Fa color="#fff" icon={faComment} />
                            All w/ Comments
                        </button>
                    </div>
                </div>
            </div>
            <div class="bg-white rounded mx-2 mb-2 w-25">
                <div class="p-2">Filter by assignee</div>
                <div class="p-2"><AssigneeFilter user={FILTER_STACK.user.state} on:selected={handleUserFilter}/></div>

            </div>
        </div>
        <div class="bg-white rounded mb-2">
            <div class="accordion">
                <div class="accordion-item">
                    <h2 class="accordion-header">
                        <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#testDashboard-filters-{generateCollapseKey(dashboardObject, dashboardObjectType)}">
                            Extra filters
                        </button>
                    </h2>
                    <div class="accordion-collapse collapse" id="testDashboard-filters-{generateCollapseKey(dashboardObject, dashboardObjectType)}">
                        <div class="d-flex">
                            <div class="mb-2 d-inline-flex align-items-start flex-column rounded bg-white">
                                <div class="p-2">Status filter</div>
                                <div class="p-2">
                                    {#each Object.entries(TestStatus) as [name, status]}
                                        <button
                                            class="ms-2 mb-2 btn btn-sm {StatusButtonCSSClassMap?.[status]}"
                                            onclick={() => FILTER_STACK.status.state[status] = !FILTER_STACK.status.state[status]}
                                        >
                                            {#if FILTER_STACK.status.state[status]}
                                                <Fa icon={faCheckSquare}/>
                                            {:else}
                                                <Fa icon={faSquare}/>
                                            {/if}
                                            {titleCase(name.split("_").join(" ").toLowerCase())}
                                        </button>
                                    {/each}
                                </div>
                            </div>
                        </div>
                        <div class="d-flex">
                            <div class="mb-2 d-inline-flex w-50 align-items-start flex-column rounded bg-white">
                            <div class="p-2">Filter by ImageId</div>
                            <div class="p-2 w-100">
                                {#await fetchImages()}
                                    <div class="spinner-grow spinner-grow-sm"></div> Loading Images...
                                {:then images}
                                <Select
                                    --item-height="auto"
                                    --item-line-height="auto"
                                    value={imageId ? { label: imageId, value: imageId} : undefined}
                                    items={images}
                                    on:select={e => {
                                        imageId = e.detail.value;
                                        fetchStats(true);
                                    }}
                                    on:clear={() => {
                                        imageId = undefined;
                                        fetchStats(true);
                                    }}
                                    placeholder="ImageId"
                                    hideEmptyState={true}
                                    clearable={true}
                                    searchable={true}
                                />
                                {:catch err}
                                    <div class="">
                                        <Fa icon={faTimes}/> Failed fetching images.
                                    </div>
                                {/await}
                            </div>
                        </div>
                        <div class="ms-2 mb-2 d-inline-flex w-50 align-items-start flex-column rounded bg-white">
                            <div class="p-2">Filter by SCT Backend</div>
                            <div class="p-2 w-100">
                                <Select
                                    --item-height="auto"
                                    --item-line-height="auto"
                                    value={loadOptionValue(FILTER_STACK, "backend")}
                                    on:select={e => FILTER_STACK.backend.state = e.detail.value}
                                    on:clear={() => FILTER_STACK.backend.state = undefined}
                                    placeholder="Backend"
                                    items={FILTER_STACK.backend.options.map(id => { return { label: id, value: id};})}
                                    hideEmptyState={true}
                                    clearable={true}
                                    searchable={true}
                                />
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        </div>
        {@const SvelteComponent_1 = settings.flatView ? FlatViewHelper : GroupedViewHelper}
        <SvelteComponent_1>
            {#each sortedGroups(stats.groups) as groupStats (groupStats.group.id)}
                {@const SvelteComponent = settings.flatView ? TestDashboardFlatView : TestDashboardGroup}
                <SvelteComponent
                    {assigneeList}
                    {groupStats}
                    {stats}
                    {dashboardObjectType}
                    {users}
                    doFilters={(test) => doFilters(test, FILTER_STACK)}
                    bind:clickedTests={clickedTests}
                    collapsed={getCollapseState(`collapse-${groupStats.group.id}`, collapseState)}
                    filtered={hideEmptyGroup(groupStats, FILTER_STACK)}
                    on:quickSelect={handleQuickSelect}
                    on:toggleCollapse={(e) => toggleCollapse(e.detail)}
                    on:testClick={e => handleTestClick(e.detail.testStats, e.detail.groupStats)}
                />
            {/each}
        </SvelteComponent_1>
    {:else}
        <div class="d-flex align-items-center justify-content-center text-center">
            <div class="spinner-grow"></div>
            <div class="ms-2 text-bold">Loading Test Dashboard...</div>
        </div>
    {/if}
</div>
