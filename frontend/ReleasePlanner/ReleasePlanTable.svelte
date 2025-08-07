<script lang="ts">
    import { run } from 'svelte/legacy';

    import Fa from "svelte-fa";
    import { createEventDispatcher, onDestroy, onMount } from "svelte";
    import { getPicture } from "../Common/UserUtils";
    import { StatusBackgroundCSSClassMap } from "../Common/TestStatus";
    import { subUnderscores, titleCase } from "../Common/TextUtils";
    import { timestampToISODate } from "../Common/DateUtils";
    import { faArrowDown, faArrowUp } from "@fortawesome/free-solid-svg-icons";

    let {
        schedules = [],
        users = {},
        plannerData = {},
        releaseData = {},
        clickedTests = {}
    } = $props();
    let releaseStats = $state();
    let releaseStatsRefreshInterval;


    const loadCollapseState = function() {
        return JSON.parse(window.localStorage.getItem(`releasePlanState-${releaseData.id}`)) || {};
    };

    const toggleCollapse = function(collapseId, force = false, forcedState = false) {
        if (force) {
            collapseState[collapseId] = forcedState;
        } else {
            collapseState[collapseId] = !(collapseState[collapseId] || false);
        }
        window.localStorage.setItem(`releasePlanState-${releaseData.id}`, JSON.stringify(collapseState));
    };

    const getCollapseState = function(collapseId, collapseState) {
        return collapseState[collapseId] ?? false;
    };

    let collapseState = $state(loadCollapseState());

    const fetchStats = async function () {
        let params = new URLSearchParams({
            release: releaseData.release.name,
            limited: new Number(false),
            force: new Number(false),
        });
        let response = await fetch("/api/v1/release/stats/v2?" + params, { cache: "reload" });
        let json = await response.json();
        if (json.status != "ok") {
            return false;
        }
        releaseStats = json.response;
    };

    let schedulesByTest = $state({});
    const dispatch = createEventDispatcher();

    const getTestsById = function(plannerData) {
        return plannerData.tests.reduce((acc, test) => {
            acc[test.id] = test;
            return acc;
        }, {});
    };

    const sortFunc = function(lhs, rhs, invert = false) {
        let sign = invert ? -1 : 1;
        if (lhs > rhs) return 1 * sign;
        if (lhs < rhs) return -1 * sign;
        if (lhs == rhs) return 0;
    };

    const sortSchedulesByTest = function (schedules) {
        let tests = getTestsById(plannerData);
        schedulesByTest = schedules.reduce((acc, schedule) => {
            schedule.tests.forEach((test) => {
                let groupName = tests[test]?.group_name;
                let testName = tests[test]?.name;
                if (!testName) return;
                if (!acc[groupName]) {
                    acc[groupName] = {};
                }
                acc[groupName][testName] = schedule;
            });
            return acc;
        }, {});
    };

    const retrieveUser = function (id) {
        return users[id];
    };

    const retrieveGroupName = function(groupName, tests) {
        const firstTest = tests[0];

        return firstTest ? firstTest.pretty_group_name || groupName : groupName;
    };

    const onTestClick = function (test) {
        dispatch("testClick", {
            test: test,
        });
    };

    const onScheduledTestClick = function (schedule, test) {
        dispatch("scheduledTestClick", {
            schedule: schedule,
            test: test,
        });
    };

    const onSelectAllClick = function(tests) {
        dispatch("selectAllClick", {
            tests: tests,
        });
    };

    run(() => {
        sortSchedulesByTest(schedules);
    });

    onMount(() => {
        fetchStats();
        releaseStatsRefreshInterval = setInterval(() => {
            fetchStats();
        }, 60 * 1000);
        sortSchedulesByTest(schedules);
    });

    onDestroy(() => {
        clearInterval(releaseStatsRefreshInterval);
    });
</script>

<div class="my-2 bg-light-one p-2 shadow-sm rounded">
    {#if plannerData.release && releaseStats}
        <div>
            {#each Object
                .entries(plannerData.tests_by_group)
                .sort(
                    ([leftGroupName, leftTests], [rightGroupName, rightTests]) => sortFunc(retrieveGroupName(leftGroupName, leftTests).toLowerCase(), retrieveGroupName(rightGroupName, rightTests).toLowerCase())
                ) as [groupName, tests] (groupName)}
            {@const prettyName = tests[0]?.pretty_group_name ?? groupName}
            {@const groupStats = releaseStats?.groups[tests[0].group_id]}
                <div class="mb-2 rounded bg-white p-2">
                    <div
                        class="fw-bold align-items-center d-flex mb-2"
                    >
                        <div>{prettyName || groupName}</div>
                        <div
                            class:d-none={getCollapseState(`collapse-${groupStats.group.id}`, collapseState)}
                            class:ms-auto={!getCollapseState(`collapse-${groupStats.group.id}`, collapseState)}
                        >
                            <button class="btn btn-dark btn-sm" onclick={() => onSelectAllClick(tests)}>Select All</button>
                        </div>
                        <div
                            class:ms-2={!getCollapseState(`collapse-${groupStats.group.id}`, collapseState)}
                            class:ms-auto={getCollapseState(`collapse-${groupStats.group.id}`, collapseState)}
                        >
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
                        </div>
                    </div>
                    <div class="collapse" class:show={!getCollapseState(`collapse-${groupStats.group.id}`, collapseState)} id="collapse-{groupStats.group.id}">
                        <div class="bg-light-two rounded p-2 mb-2 d-flex flex-wrap">
                        {#each tests.sort((a, b) => sortFunc(a.name, b.name)) as test (test.id)}
                        {@const testStats = releaseStats?.["groups"]?.[test.group_id]?.["tests"]?.[test.id] ?? {}}
                        {@const testSchedule = schedulesByTest?.[groupName]?.[test.name]}
                                <div
                                    class="rounded bg-main status-block m-1 d-flex flex-column overflow-hidden shadow-sm position-relative"
                                    class:border-assigned={testSchedule}
                                    role="button"
                                    tabindex="0"
                                    onkeypress={() => {
                                        testSchedule ? onScheduledTestClick(testSchedule, test) : onTestClick(test);
                                    }}
                                    onclick={() => {
                                        testSchedule ? onScheduledTestClick(testSchedule, test) : onTestClick(test);
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
                                    </div>
                                    <div class="d-flex flex-fill flex-column">
                                        <div class="p-1 text-small d-flex align-items-center">
                                            <div class="ms-1">{testStats?.test?.name ?? test.name}
                                            {#if testStats.buildNumber}
                                                - <span class="fw-bold">#{testStats.buildNumber}</span> <span class="text-muted">({timestampToISODate(testStats.start_time).split(" ")[0]})</span>
                                            {/if}
                                            </div>
                                        </div>
                                        <div class="text-end d-flex flex-fill align-items-end justify-content-end">
                                            {#if testSchedule}
                                                {#each testSchedule.assignees as assignee}
                                                    <div class="p-1" title={retrieveUser(assignee)?.full_name ?? "Ghost"}>
                                                        <span>{retrieveUser(assignee)?.full_name ?? "Ghost"}</span>
                                                        <img
                                                            class="img-thumb"
                                                            src={getPicture(retrieveUser(assignee)?.picture_id)}
                                                            alt={retrieveUser(assignee)?.full_name ?? "Ghost"}
                                                        />
                                                    </div>
                                                {/each}
                                            {:else}
                                                <!-- Empty -->
                                            {/if}
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
                </div>
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

    .border-assigned {
        border: 3px solid #42ffd0 !important;
    }

    .group-cell {
        width: 8rem;
    }
</style>
