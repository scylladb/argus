<script lang="ts">
    import { run } from 'svelte/legacy';

    import { createEventDispatcher, onMount } from "svelte";
    import * as chrono from "chrono-node";
    import Schedule from "./Schedule.svelte";

    let { schedules = [], releaseData = {}, users = {} } = $props();
    const dispatch = createEventDispatcher();
    let dates = $state([]);
    let groups = $state({});
    let clickedCell = $state("");
    let selectedGroups = $state({});
    let today = $state(new Date());
    run(() => {
        today.setHours(0, today.getTimezoneOffset() * -1, 0, 0);
    });

    const generateDates = function () {
        const weekRange = Array.from({ length: 18 }, (v, k) => -4 + k);
        const startOfTheWeekDay = chrono.parseDate("This Monday UTC", today);
        dates = weekRange.map((week) => {
            let thisWeek = new Date(startOfTheWeekDay);
            thisWeek.setHours(24 * 7 * week + startOfTheWeekDay.getHours());
            return {
                date: thisWeek,
                dateKey: thisWeek.toISOString().split("T").shift(),
                dateIndex: week,
                highlight: week == 0,
            };
        });
    };

    const getStartOfTheWeekForDay = function(date) {
        return chrono.parseDate("Next Monday UTC", date);
    };

    const prepareGroups = function () {
        selectedGroups = {};
        groups = releaseData.groups.reduce((acc, group) => {
            let groupWithSchedules = Object.assign(group);
            groupWithSchedules.schedules = schedules
                .filter(schedule => schedule.groups.includes(group.id))
                .reduce((acc, schedule) => {
                    let dateKey = getStartOfTheWeekForDay(new Date(schedule.period_start))
                        .toISOString()
                        .split("T")
                        .shift();
                    acc[dateKey] = schedule;
                    return acc;
                }, {});
            acc.push(groupWithSchedules);
            return acc;
        }, []);
    };

    const onAssigneeCellClick = function(schedule, group, date) {
        if (schedule) {
            if (clickedCell == `${group.name}/${date.dateKey}`) {
                return;
            }
            clickedCell = `${group.name}/${date.dateKey}`;
            return;
        };
        clickedCell = "";
        if (Object.keys(selectedGroups).length == 1 && !selectedGroups[date.dateKey]) {
            selectedGroups = {};
            dispatch("clearGroups", {
                selected: []
            });
        }
        let groupsToHighlight = selectedGroups[date.dateKey] ?? [];
        if (groupsToHighlight.findIndex(val => val == group.name) == -1) {
            groupsToHighlight.push(group.name);
        } else {
            groupsToHighlight = groupsToHighlight.filter(value => value != group.name);
            dispatch("clearGroups", {
                selected: groupsToHighlight
            });
            selectedGroups[date.dateKey] = groupsToHighlight;
            return;
        }
        selectedGroups[date.dateKey] = groupsToHighlight;

        dispatch("cellClick", {
            schedule: schedule,
            group: group,
            date: date
        });
    };

    run(() => {
        generateDates(today);
    });
    run(() => {
        prepareGroups(schedules);
    });
</script>

<div class="my-2 table-main">
    <div class="mb-2 d-flex">
        <div class="w-10">
            <label class="form-label" for="dateTableSelection"
                >Today</label
            >
            <input
                class="form-control"
                type="date"
                id="dateTableSelection"
                value={today.toISOString().split("T").shift()}
                onchange={(e) => {
                    today = new Date(e.target.value);
                }}
            />
        </div>
    </div>
    <table class="table table-sm table-bordered border-dark m-0">
        <thead>
            <tr>
                <th>Group</th>
                {#each dates as date (date.dateKey)}
                    <th
                        class="header-sm border-dark"
                        class:table-info={date.highlight}
                        class:table-secondary={date.dateIndex < 0}
                        class:cursor-question={date.highlight}
                        title={date.highlight ? "This week" : ""}
                        >{date.date.toLocaleDateString('en-CA', { timeZone: 'UTC' })}</th
                    >
                {/each}
            </tr>
        </thead>
        <tbody>
            {#each groups as group (group.name)}
                <tr>
                    <td
                        >{group.pretty_name || group.name}</td
                    >
                    {#each dates as date}
                        <td
                            class:table-info={date.highlight && !group.schedules[date.dateKey]}
                            class:table-success={group.schedules[date.dateKey]}
                            class:table-warning={(selectedGroups[date.dateKey] ?? []).includes(group.name)}
                            class:table-secondary={date.dateIndex < 0 && !group.schedules[date.dateKey]}
                            class="cell-sm cursor-pointer position-relative border-dark"
                            onclick={() => {onAssigneeCellClick(group.schedules[date.dateKey], group, date)}}
                        >
                            {#if group.schedules[date.dateKey]}
                                {users[group.schedules[date.dateKey].assignees[0]]?.full_name ?? "#EMPTY"}
                            {/if}
                            {#if clickedCell == `${group.name}/${date.dateKey}`}
                            <Schedule
                                {releaseData}
                                scheduleData={group.schedules[date.dateKey]}
                                {users}
                                on:closeSchedule={(e) => {
                                    clickedCell = "";
                                }}
                                on:deleteSchedule={
                                    (e) => {
                                        clickedCell = "";
                                        dispatch("tableDeleteSchedule", e.detail);
                                    }
                                }
                                on:clearGroups
                                on:refreshSchedules
                            />
                            {/if}
                        </td>
                    {/each}
                </tr>
            {/each}
        </tbody>
    </table>
</div>

<style>
    .table-main {
        overflow-x: none;
    }

    .header-sm {
        padding: 2px;
        font-size: 0.6em;
        vertical-align: middle;
        text-align: center;
    }

    .cell-sm {
        padding: 2px;
        font-size: 1.2em;
        vertical-align: middle;
        text-align: center;
    }

    .cursor-question {
        cursor: help;
    }

    .cursor-pointer {
        cursor: pointer;
    }

</style>
