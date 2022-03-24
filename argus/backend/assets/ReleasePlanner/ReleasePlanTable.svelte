<script>
    import Fa from "svelte-fa";
    import { faCircle } from "@fortawesome/free-solid-svg-icons";
    import { createEventDispatcher, onMount } from "svelte";
    import { releaseRequests, stats } from "../Stores/StatsSubscriber";
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
    let releaseStats = undefined;

    releaseRequests.update((val) => [...val, releaseData.release.name]);
    stats.subscribe((val) => {
        releaseStats = val["releases"]?.[releaseData.release.name] ?? {};
    });

    let schedulesByTest = {};
    const dispatch = createEventDispatcher();
    const sortSchedulesByTest = function (schedules) {
        schedulesByTest = schedules.reduce((acc, schedule) => {
            schedule.tests.forEach((test) => {
                let [groupName, testName] = test.split("/");
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
            selectedSchedule == `${schedule.schedule_id}-${cellIndex}`
        ) {
            selectedSchedule = "";
            return;
        } else if (schedule) {
            selectedSchedule = `${schedule.schedule_id}-${cellIndex}`;
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
        sortSchedulesByTest(schedules);
    });
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
                                    {groupName}
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
                                                        groupName
                                                    ]?.["tests"]?.[test.name]
                                                        ?.status ?? "unknown"
                                                ]}
                                                title={releaseStats?.[
                                                    "groups"
                                                ]?.[groupName]?.["tests"]?.[
                                                    test.name
                                                ].status ?? "unknown / not run"}
                                            >
                                                <Fa icon={faCircle} />
                                            </div>
                                            <div class="ms-2">
                                                {test.name}
                                            </div>
                                        </div>
                                    </div>
                                    <div class="ms-auto">
                                        <a
                                            href={`https://jenkins.scylladb.com/job/${releaseData.release.name}/job/${groupName}/job/${test.name}`}
                                            class="btn btn-sm btn-outline-dark"
                                            target="_blank"
                                        >
                                            Jenkins URL
                                        </a>
                                    </div>
                                </div>
                                {#if `${schedulesByTest?.[groupName]?.[test.name]?.schedule_id}-${idx}` == selectedSchedule}
                                    <Schedule
                                        scheduleData={schedulesByTest[
                                            groupName
                                        ][test.name]}
                                        {releaseData}
                                        {users}
                                        on:deleteSchedule
                                        on:refreshSchedules
                                    />
                                {/if}
                            </td>
                            <td>
                                <CommentTableRow
                                    bind:commentText={test.comment}
                                    release={releaseData.release.name}
                                    group={groupName}
                                    test={test.name}
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
        width: 12rem;
    }
</style>
