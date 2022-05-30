<script>
    import Fa from "svelte-fa";
    import { faCircle } from "@fortawesome/free-solid-svg-icons";
    import { createEventDispatcher, onDestroy, onMount } from "svelte";
    import { getPicture } from "../Common/UserUtils";
    import { StatusCSSClassMap } from "../Common/TestStatus";
    import Schedule from "./Schedule.svelte";
    import CommentTableRow from "./CommentTableRow.svelte";

    export let schedules = [];
    export let users = {};
    export let plannerData = {};
    export let releaseData = {};
    export let clickedTests = {};
    let selectedSchedule = "";
    let releaseStats;
    let releaseStatsRefreshInterval;

    const fetchStats = async function () {
        let params = new URLSearchParams({
            release: releaseData.release.name,
            limited: new Number(false),
            force: new Number(false),
        });
        let response = await fetch("/api/v1/release/stats/v2?" + params);
        let json = await response.json();
        if (json.status != "ok") {
            return false;
        }
        releaseStats = json.response;
    };

    let schedulesByTest = {};
    const dispatch = createEventDispatcher();

    const getTestsById = function(plannerData) {
        return plannerData.tests.reduce((acc, test) => {
            acc[test.id] = test;
            return acc;
        }, {});
    }

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

    const onCellClick = function (test, group, schedule, cellIndex) {
        if (
            schedule &&
            selectedSchedule == `${schedule.id}-${cellIndex}`
        ) {
            selectedSchedule = "";
            return;
        } else if (schedule) {
            selectedSchedule = `${schedule.id}-${cellIndex}`;
            return;
        }
        selectedSchedule = "";
        dispatch("cellClick", {
            test: test,
            group: group,
        });
    };

    $: sortSchedulesByTest(schedules);

    onMount(() => {
        fetchStats();
        releaseStatsRefreshInterval = setInterval(() => {
            fetchStats();
        }, 60 * 1000);
        sortSchedulesByTest(schedules);
    });

    onDestroy(() => {
        clearInterval(releaseStatsRefreshInterval);
    })
</script>

<div class="my-2">
    {#if plannerData.release && releaseStats}
        <table class="table border table-bordered table-hover">
            <thead>
                <th>Group</th>
                <th>Test</th>
                <th>Comment</th>
                <th>Assignee</th>
            </thead>
            <tbody>
                {#each Object.entries(plannerData.tests_by_group) as [groupName, tests] (groupName)}
                    {#each tests as test, idx}
                        <tr>
                            {#if idx == 0}
                                <td
                                    class="group-cell fs-2 fw-bold align-middle"
                                    rowspan={tests.length}
                                >
                                    {tests[0].pretty_group_name || groupName}
                                </td>
                            {/if}
                            <td
                                class="test-cell position-relative align-middle"
                                class:table-success={clickedTests[
                                    `${groupName}/${test.name}`
                                ]}
                                class:table-warning={schedulesByTest?.[
                                    groupName
                                ]?.[test.name]}
                            >
                                <div class="d-flex align-items-between">
                                    <div
                                        class="border rounded p-1 px-2 cursor-pointer"
                                        on:click={() => {
                                            onCellClick(
                                                test,
                                                groupName,
                                                schedulesByTest?.[groupName]?.[
                                                    test.name
                                                ],
                                                idx
                                            );
                                        }}
                                    >
                                        <div class="d-flex align-items-center">
                                            <div
                                                class={StatusCSSClassMap[
                                                    releaseStats?.["groups"]?.[
                                                        test.group_id
                                                    ]?.["tests"]?.[test.id]
                                                        ?.status ?? "unknown"
                                                ]}
                                                title={releaseStats?.[
                                                    "groups"
                                                ]?.[test.group_id]?.["tests"]?.[
                                                    test.id
                                                ].status ?? "unknown / not run"}
                                            >
                                                <Fa icon={faCircle} />
                                            </div>
                                            <div class="ms-2">
                                                {test.name}
                                            </div>
                                        </div>
                                    </div>
                                    {#if test.build_system_url}
                                        <div class="ms-auto">
                                            <a
                                                href={test.build_system_url}
                                                class="btn btn-sm btn-outline-dark"
                                                target="_blank"
                                            >
                                                Jenkins URL
                                            </a>
                                        </div>
                                    {/if}
                                </div>
                                {#if `${schedulesByTest?.[groupName]?.[test.name]?.id}-${idx}` == selectedSchedule}
                                    <Schedule
                                        scheduleData={schedulesByTest[
                                            groupName
                                        ][test.name]}
                                        {releaseData}
                                        {users}
                                        on:deleteSchedule
                                        on:refreshSchedules
                                        on:closeSchedule={(e) => {
                                            selectedSchedule = "";
                                        }}
                                    />
                                {/if}
                            </td>
                            <td>
                                <CommentTableRow
                                    bind:commentText={test.comment}
                                    release={releaseData.release.id}
                                    group={test.group_id}
                                    test={test.id}
                                />
                            </td>
                            <td
                                class:table-secondary={!schedulesByTest?.[
                                    groupName
                                ]?.[test.name]}
                            >
                                {#if schedulesByTest?.[groupName]?.[test.name]}
                                    <div class="d-flex">
                                        {#each schedulesByTest[groupName][test.name].assignees as assignee}
                                            {#if retrieveUser(assignee)}
                                                <div
                                                    class="d-flex align-items-center border rounded mb-2 p-2 me-2"
                                                >
                                                    <img
                                                        class="profile-thumbnail"
                                                        src={getPicture(
                                                            retrieveUser(
                                                                assignee
                                                            ).picture_id
                                                        )}
                                                        alt={retrieveUser(
                                                            assignee
                                                        ).full_name}
                                                    />
                                                    <div class="ms-2">
                                                        {retrieveUser(assignee)
                                                            .full_name}
                                                        <div class="text-muted">
                                                            {retrieveUser(
                                                                assignee
                                                            ).username}
                                                        </div>
                                                    </div>
                                                </div>
                                            {/if}
                                        {/each}
                                    </div>
                                {:else}
                                    <!-- Empty -->
                                {/if}
                            </td>
                        </tr>
                    {/each}
                {/each}
            </tbody>
        </table>
    {:else}
        <div class="col d-flex align-items-center justify-content-center">
            <div class="spinner-border me-3 text-muted" />
            <div class="display-6 text-muted">Loading table...</div>
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

    .group-cell {
        width: 8rem;
    }
</style>
