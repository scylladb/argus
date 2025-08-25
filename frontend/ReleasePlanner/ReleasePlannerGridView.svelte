<script lang="ts">
    import Fa from "svelte-fa";
    import { createEventDispatcher, onDestroy, onMount } from "svelte";
    import { StatusBackgroundCSSClassMap } from "../Common/TestStatus";
    import { subUnderscores, titleCase } from "../Common/TextUtils";
    import { timestampToISODate } from "../Common/DateUtils";
    import { faArrowDown, faArrowUp } from "@fortawesome/free-solid-svg-icons";
    import { faTimesCircle } from "@fortawesome/free-regular-svg-icons";

    interface Props {
        release?: any;
        mode?: string;
        format?: string;
        groupOnly?: boolean;
        existingPlans?: any;
        selectingFor: any;
    }

    let {
        release = {},
        mode = "multi",
        format = "list",
        groupOnly = false,
        existingPlans = [],
        selectingFor
    }: Props = $props();
    let filterToParent = $state(!!(selectingFor?.created_from));
    let filterExecuted = $state(false);
    let clickedTests = $state({});
    let clickedGroups = $state({});
    let releaseStats = $state();
    let gridView = $state();
    let header = $state();
    let observer;
    let sticky = $state(false);
    let releaseStatsRefreshInterval;
    const dispatch = createEventDispatcher();

    const loadCollapseState = function() {
        return JSON.parse(window.localStorage.getItem(`releasePlanGridViewState-${release.id}`)) || {};
    };

    const toggleCollapse = function(collapseId, force = false, forcedState = false) {
        if (force) {
            collapseState[collapseId] = forcedState;
        } else {
            collapseState[collapseId] = !(collapseState[collapseId] || false);
        }
        window.localStorage.setItem(`releasePlanGridViewState-${release.id}`, JSON.stringify(collapseState));
    };

    const getCollapseState = function(collapseId, collapseState) {
        return collapseState[collapseId] ?? false;
    };

    let collapseState = $state(loadCollapseState());

    const getGridView = async function () {
        let response = await fetch(`/api/v1/planning/release/${release.id}/gridview`, { cache: "reload" });
        let json = await response.json();
        if (json.status != "ok") {
            return false;
        }
        gridView = json.response;
    };

    const fetchStats = async function () {
        let params = new URLSearchParams({
            release: release.name,
            productVersion: selectingFor?.target_version ?? "",
            limited: new Number(false),
            force: new Number(true),
        });
        let response = await fetch("/api/v1/release/stats/v2?" + params, { cache: "reload" });
        let json = await response.json();
        if (json.status != "ok") {
            return false;
        }
        releaseStats = json.response;
    };


    const sortFunc = function(lhs, rhs, invert = false) {
        let sign = invert ? -1 : 1;
        if (lhs > rhs) return 1 * sign;
        if (lhs < rhs) return -1 * sign;
        if (lhs == rhs) return 0;
    };

    const retrieveGroupName = function(groupId) {
        const group = gridView.groups[groupId];
        return (group?.pretty_name || group?.name) ?? "#NO_GROUP";
    };

    const onTestClick = function (test) {
        clickedTests[test.id] = !clickedTests[test.id];
        if (clickedGroups[test.group_id]) {
            clickedGroups[test.group_id] = false;
        }
        if (mode == "single") onConfirmClick();
    };

    const onConfirmClick = function() {
        const selectedGroups = Object
            .entries(clickedGroups)
            .filter(([_, selected]) => selected)
            .map(([gid, _]) => gridView.groups[gid]);
        const selectedTests = Object
            .entries(clickedTests)
            .filter(([_, selected]) => selected)
            .map(([tid, _]) => gridView.tests[tid]);
        if (format == "list") {
            let items = [...selectedGroups, ...selectedTests];
            dispatch("gridViewConfirmed", {
                items: items,
            });
        } else if (format == "map") {
            dispatch("gridViewConfirmed", {
                tests: selectedTests,
                groups: selectedGroups,
            });
        }
    };

    const planned = (plans) => {
        return plans
            .map(({tests, groups}) => [...tests, ...groups])
            .reduce((acc, val) => [...acc, ...val], []);
    };

    const shouldFilterIfParent = function (entity, parentEntity, filterEnabled, checkChildren = false, children = []) {
        if (checkChildren && children.filter(ent => !shouldFilterIfParent(ent, null, filterEnabled)).length > 0) {
            return false;
        }
        if (selectingFor?.created_from) {
            const parentPlan = existingPlans.filter((plan) => plan.id == selectingFor?.created_from);
            const parentFilter = !(planned(parentPlan).includes(entity.id) != planned(parentPlan).includes(parentEntity?.id)); //xor, to handle showing tests for selected groups.
            return filterEnabled ? parentFilter : false;
        }
        return false;
    };

    const shouldFilterIfExecuted = function (entity, parentEntity, filterEnabled, checkChildren = false, children = []) {
        if (checkChildren && children.filter(ent => shouldFilterIfExecuted(ent, entity, filterEnabled)).length > 0) {
            return false;
        }
        if (selectingFor?.created_from) {
            const relatedPlans = existingPlans.filter((plan) => plan.created_from == selectingFor?.created_from);
            const alreadyInExecution = planned(relatedPlans).includes(entity.id);
            return filterEnabled ? alreadyInExecution : false;
        }
        return false;
    };

    const onSelectGroupClick = function(group) {
        clickedGroups[group.id] = !clickedGroups[group.id];
        gridView.testByGroup[group.id].forEach(test => clickedTests[test.id] = false);
        if (mode == "single") onConfirmClick();
    };

    onMount(async () => {
        observer = new IntersectionObserver((entries) => {
            let entry = entries[0];
            if (!entry) return;
            if (entry.intersectionRatio == 0 && !entry.isIntersecting) {
                sticky = true;
            } else {
                sticky = false;
            }
        }, {
            threshold: [0, 0.25, 0.5, 0.75, 1]
        });
        observer.observe(header);
        getGridView();
        fetchStats();
        releaseStatsRefreshInterval = setInterval(() => {
            fetchStats();
        }, 60 * 1000);
    });

    onDestroy(() => {
        observer.disconnect();
        clearInterval(releaseStatsRefreshInterval);
    });
</script>

<div bind:this={header}></div>
{#if [...Object.keys(clickedTests), ...Object.keys(clickedGroups)].length > 0 && mode == "multi"}
    <div class="p-2 bg-light-three rounded" class:sticky={sticky} class:shadow={sticky}>
        <div class="d-flex align-items-center flex-wrap mb-2 p-2 bg-white rounded">
            {#each Object.entries(clickedTests) as [testId, clicked] (testId)}
                {#if clicked}
                    <div class="bg-primary text-white rounded-pill d-flex align-items-center ms-2 mb-2 px-2" style="overflow: hidden">
                        <div>
                            <span class="fw-bold">T</span> {gridView.tests[testId].name}
                        </div>
                        <div class="ms-1">
                            <button class="btn btn-sm btn-primary" onclick={() => (clickedTests[testId] = false)}><Fa icon={faTimesCircle}/></button>
                        </div>
                    </div>
                {/if}
            {/each}
            {#each Object.entries(clickedGroups) as [groupId, clicked] (groupId)}
                {@const group = gridView.groups[groupId]}
                {#if clicked}
                    <div class="bg-success text-white rounded-pill d-flex align-items-center ms-2 mb-2 px-2" style="overflow: hidden">
                        <div>
                            <span class="fw-bold">G</span> {group.pretty_name || group.name}
                        </div>
                        <div class="ms-1">
                            <button class="btn btn-sm btn-success" onclick={() => (clickedGroups[groupId] = false)}><Fa icon={faTimesCircle}/></button>
                        </div>
                    </div>
                {/if}
            {/each}
        </div>
        <div>
            <button class="btn btn-primary w-100" onclick={onConfirmClick}>Confirm</button>
        </div>
    </div>
{/if}
<div class="my-2 bg-light-one p-2 shadow-sm rounded">
    {#if gridView && releaseStats}
        <div>
            {#if selectingFor}
                <div class="form-check form-switch">
                    <input
                        class="form-check-input"
                        type="checkbox"
                        role="switch"
                        title="Hide tests that have been planned for this release"
                        bind:checked={filterToParent}
                        id="gridViewFilterExisting"
                    />
                    <label
                        class="form-check-label"
                        for="gridViewFilterExisting">Scope to Parent Plan</label
                    >
                </div>
                <div class="form-check form-switch">
                    <input
                        class="form-check-input"
                        type="checkbox"
                        role="switch"
                        title="Hide tests that have been planned for this release"
                        bind:checked={filterExecuted}
                        id="gridViewFilterExisting"
                    />
                    <label
                        class="form-check-label"
                        for="gridViewFilterExisting">Hide already planned for execution</label
                    >
                </div>
            {/if}
        </div>
        <div>
            {#each Object
                .entries(gridView.testByGroup)
                .sort(
                    ([leftGroupId], [rightGroupId]) => sortFunc(retrieveGroupName(leftGroupId).toLowerCase(), retrieveGroupName(rightGroupId).toLowerCase())
                ) as [groupId, tests] (groupId)}
            {@const group = gridView.groups[groupId] ?? {}}
            {@const prettyName = group?.pretty_name ?? group?.name}
            {@const groupStats = releaseStats?.groups?.[group?.id]}
            {#if group && groupStats}
                <div
                    class="mb-2 rounded bg-white p-2 border-success"
                    class:border={clickedGroups[group.id]}
                    style="border-size: 4px"
                    class:d-none={shouldFilterIfParent(group, null, filterToParent, true, tests) || shouldFilterIfExecuted(group, null, filterExecuted, true, tests)}
                >
                    <div
                        class="fw-bold align-items-center d-flex mb-2"
                    >
                        <div>{prettyName}</div>
                        {#if clickedGroups[group.id]}
                            <div class="fw-light ms-2 rounded-pill px-2 text-success border border-success">Selected</div>
                        {/if}
                        <div
                            class:d-none={getCollapseState(`collapse-${groupStats.group.id}`, collapseState)}
                            class:ms-auto={!getCollapseState(`collapse-${groupStats.group.id}`, collapseState)}
                        >
                            <button class="btn btn-dark btn-sm" onclick={() => onSelectGroupClick(group)}>Select Group</button>
                        </div>
                        <div
                            class:ms-2={!getCollapseState(`collapse-${groupStats.group.id}`, collapseState)}
                            class:ms-auto={getCollapseState(`collapse-${groupStats.group.id}`, collapseState)}
                        >
                            {#if !groupOnly}
                                <button
                                    class="btn btn-sm"
                                    data-bs-toggle="collapse"
                                    data-bs-target="#collapse-{groupStats.group.id}"
                                    onclick={() => toggleCollapse(`collapse-${groupStats.group.id}`)}
                                >
                                {#if getCollapseState(`collapse-${groupStats.group.id}`, collapseState)}
                                    <Fa icon={faArrowDown}/>
                                {:else}
                                    <Fa icon={faArrowUp}/>
                                {/if}
                                </button>
                            {/if}
                        </div>
                    </div>
                    {#if !groupOnly}
                        <div class="collapse" class:show={!getCollapseState(`collapse-${groupStats.group.id}`, collapseState)} id="collapse-{groupStats.group.id}">
                            <div class="bg-light-two rounded p-2 mb-2 d-flex flex-wrap">
                            {#each Array.from(tests).sort((a, b) => sortFunc(a.name, b.name)) as test (test.id)}
                            {@const testStats = releaseStats?.["groups"]?.[test.group_id]?.["tests"]?.[test.id] ?? {}}
                                    <div
                                        class="rounded bg-main status-block m-1 d-flex flex-column overflow-hidden shadow-sm position-relative"
                                        role="button"
                                        tabindex="0"
                                        class:d-none={shouldFilterIfParent(test, group, filterToParent) || shouldFilterIfExecuted(test, group, filterExecuted)}
                                        onkeypress={() => {
                                            onTestClick(test);
                                        }}
                                        onclick={() => {
                                            onTestClick(test);
                                        }}
                                    >
                                        <div
                                            class="{StatusBackgroundCSSClassMap[testStats.status]} text-center text-light p-1 border-bottom"
                                        >
                                            {testStats.status == "unknown"
                                                ? "Not run"
                                                : subUnderscores(testStats.status ?? "Unknown").split(" ").map(v => titleCase(v)).join(" ")}
                                            {#if clickedTests[test.id]}
                                                <div class="text-tiny">Selected</div>
                                            {/if}
                                            {#if clickedGroups[test.group_id]}
                                                <div class="text-tiny">Selected by group</div>
                                            {/if}
                                        </div>
                                        <div class="d-flex flex-fill flex-column">
                                            <div class="p-1 text-small d-flex align-items-center">
                                                <div class="ms-1">{testStats?.test?.name ?? test.name}
                                                {#if testStats.buildNumber}
                                                    - <span class="fw-bold">#{testStats.buildNumber}</span> <span class="text-muted">({timestampToISODate(testStats.start_time).split(" ")[0]})</span>
                                                {/if}
                                                </div>
                                            </div>
                                        </div>
                                        {#if test.comment}
                                            <div class="border-top text-center">
                                                <span class="text-muted text-small">{test.comment}</span>
                                            </div>
                                        {/if}
                                    </div>
                            {/each}
                            </div>
                        </div>
                    {/if}
                </div>
            {/if}
            {/each}
        </div>
    {:else}
        <div class="col d-flex align-items-center justify-content-center">
            <div class="spinner-border me-3 text-muted"></div>
            <div class="display-6 text-muted">Loading...</div>
        </div>
    {/if}
</div>


<style>
    .cursor-pointer {
        cursor: pointer;
    }

    .profile-thumbnail {
        width: 32px;
        height: auto;
        border-radius: 50%;
    }

    .img-thumb {
        border-radius: 50%;
        width: 32px;
    }

    .text-small {
        font-size: 0.8em;
    }

    .text-tiny {
        font-size: 0.6em;
    }
    .status-block {
        width: 178px;
        max-height: 196px;
        box-sizing: border-box;
        cursor: pointer;
    }

    .sticky {
        position: sticky;
        top: 12px;
        z-index: 999;
        margin: 1em;
        border-radius: 4px;
    }

    .group-cell {
        width: 8rem;
    }
</style>
