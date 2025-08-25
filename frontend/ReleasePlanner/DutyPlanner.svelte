<script lang="ts">
    import { run } from 'svelte/legacy';

    import { onMount } from "svelte";
    import Select from "svelte-select";
    import User from "../Profile/User.svelte";
    import ScheduleTable from "./ScheduleTable.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    import { sendMessage } from "../Stores/AlertStore";
    import { filterUser } from "../Common/SelectUtils";
    import {
        startDate,
        endDate,
        timestampToISODate
    } from "../Common/DateUtils";
    import { faArrowAltCircleRight, faCalendar, faFlagCheckered } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    let { releaseData = {}, schedules = $bindable([]) } = $props();
    let users = $state({});
    run(() => {
        users = $userList;
    });
    let selectedGroups = $state([]);
    let selectedTests = $state([]);

    const PayloadTemplate = {
        releaseId: releaseData.release.id,
        groups: [],
        tests: [],
        start: undefined,
        end: undefined,
        assignees: [],
        tag: "",
    };

    const handleDateChange = function(value) {
        newScheduleDate = startDate(releaseData.release, value);
        newScheduleEndDate = endDate(releaseData.release, newScheduleDate);

        newSchedule.start = timestampToISODate(newScheduleDate.getTime());
        newSchedule.end =  timestampToISODate(newScheduleEndDate.getTime());
    };

    let newSchedule = Object.assign(PayloadTemplate);
    let newScheduleDate = $state(startDate(releaseData.release));
    let newScheduleEndDate = $state(endDate(releaseData.release, newScheduleDate));

    const fetchSchedules = async function () {
        try {
            let params = new URLSearchParams({
                releaseId: releaseData.release.id,
            }).toString();
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
                    "DutyPlanner::fetchSchedules"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during schedule fetch",
                    "DutyPlanner::fetchSchedules"
                );
            }
        }
    };

    const submitNewSchedule = async function () {
        try {
            let apiResponse = await fetch("/api/v1/release/schedules/submit", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(newSchedule),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                handleClearGroups();
                fetchSchedules();

            } else {
                throw apiJson;
            }
            newSchedule = Object.assign(PayloadTemplate);
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to submit schedule.\nAPI Response: ${error.response.arguments[0]}`,
                    "DutyPlanner::submitNewSchedule"
                );
            } else {
                console.log(error);
                sendMessage(
                    "error",
                    "A backend error occurred during schedule submission",
                    "DutyPlanner::submitNewSchedule"
                );
            }
        }
    };

    const deleteSchedule = async function (event) {
        let scheduleId = event.detail.id;
        try {
            let apiResponse = await fetch("/api/v1/release/schedules/delete", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    releaseId: releaseData.release.id,
                    scheduleId: scheduleId,
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                fetchSchedules();
                handleClearGroups();

            } else {
                throw apiJson;
            }
            newSchedule = Object.assign(PayloadTemplate);
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to delete schedule.\nAPI Response: ${error.response.arguments[0]}`,
                    "DutyPlanner::deleteSchedule"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during schedule deletion",
                    "DutyPlanner::deleteSchedule"
                );
            }
        }
    };

    const extractGroups = function (releaseData) {
        return Object.values(releaseData.groups).map((val) => {
            return {
                label: val.pretty_name || val.name,
                value: val.id,
            };
        });
    };

    const prepareUsers = function (users) {
        return Object.values(users)
            .map((val) => {
                return {
                    label: val.username,
                    value: val.id,
                    picture_id: val.picture_id,
                    full_name: val.full_name,
                };
            })
            .sort((a, b) => {
                if (a.value > b.value) {
                    return 1;
                } else if (b.value > a.value) {
                    return -1;
                }
                return 0;
            });
    };

    const extractTests = function (releaseData) {
        return Object.values(releaseData.tests)
            .map((val) => {
                return {
                    label: val.name,
                    value: val.name,
                };
            })
            .sort((a, b) => {
                if (a.value > b.value) {
                    return 1;
                } else if (b.value > a.value) {
                    return -1;
                }
                return 0;
            });
    };

    const handleCellClick = function(e) {
        let data = e.detail;
        if (data.schedule) return;
        handleDateChange(data.date.dateKey);
        if (!selectedGroups) {
            selectedGroups = [];
        }
        if (selectedGroups.findIndex(val => val.value == data.group.id) == -1) {
            selectedGroups.push({ label: data.group.pretty_name || data.group.name, value: data.group.id });
            selectedGroups = selectedGroups;
            handleGroupSelect({
                detail: selectedGroups
            });
        }
    };

    const handleClearGroups = function(e) {
        let selected = e?.detail?.selected ?? [];
        console.log(selected);
        selectedGroups = selectedGroups?.filter(group => selected.includes(group.value)) ?? [];
        handleGroupSelect({
            detail: selectedGroups
        });
    };

    const handleTestSelect = function (e) {
        newSchedule.tests =
            e.detail?.map((val) => {
                return val.value;
            }) ?? [];
        newSchedule = newSchedule;
    };
    const handleGroupSelect = function (e) {
        newSchedule.groups =
            e.detail?.map((val) => {
                return val.value;
            }) ?? [];
        newSchedule = newSchedule;
    };
    const handleAssigneeSelect = function (e) {
        newSchedule.assignees = [e.detail.value];
        newSchedule = newSchedule;
    };

    onMount(() => {
        fetchSchedules();
    });
</script>

<div class="container-fluid border rounded bg-white my-3 min-vh-100 shadow-sm">
    <div class="row">
        <div class="p-2 display-6">{releaseData.release.name}</div>
        <div>
            <a class="btn btn-primary" href="/release/{releaseData.release.name}/scheduler"><Fa icon={faCalendar}/> Test Planner</a>
        </div>
    </div>
    {#if !releaseData.release.perpetual}
        <div class="row">
            <div class="col p-2">
                <div class="rounded p-2 border-warning border bg-warning bg-opacity-50">
                    <b>Important:</b> Not supported for non-weekly schedules yet!
                </div>
            </div>
        </div>
    {/if}
    <div class="row">
        {#if Object.values(users).length > 0}
            <ScheduleTable
                {releaseData}
                {users} {schedules}
                on:cellClick={handleCellClick}
                on:tableDeleteSchedule={deleteSchedule}
                on:clearGroups={handleClearGroups}
                on:refreshSchedules={() => fetchSchedules()}
            />
        {/if}
    </div>
    <div class="row">
        {#if Object.values(users).length > 0}
            <div class="col border rounded m-3 p-3">
                <h4 class="mb-3">New plan</h4>
                <div class="d-flex align-items-start justify-content-center">
                    <div class="me-3 w-25">
                        <div class="mb-3">
                            <label
                                for="newScheduleReleaseName"
                                class="form-label">Release</label
                            >
                            <input
                                id="newScheduleReleaseName"
                                class="form-control"
                                type="text"
                                value={releaseData.release.name}
                                disabled
                            />
                        </div>
                    </div>
                    <div class="me-3 w-25">
                        <div class="mb-3">
                            <div class="form-label">Groups</div>
                            <Select
                                items={extractGroups(releaseData)}
                                multiple={true}
                                placeholder="Select groups"
                                on:select={handleGroupSelect}
                                bind:value={selectedGroups}
                            />
                        </div>
                        <div class="mb-3 d-none">
                            <div class="form-label">Tests</div>
                            <Select
                                items={extractTests(releaseData)}
                                multiple={true}
                                placeholder="Select tests"
                                bind:value={selectedTests}
                                on:select={handleTestSelect}
                            />
                        </div>
                    </div>
                    <div class="me-3 w-25">
                        <div class="mb-1">Timing</div>
                        <div class="mb-1 p-1 text-muted rounded shadow-sm d-inline-block">
                            <Fa icon={faArrowAltCircleRight} /> Will start on {timestampToISODate(newScheduleDate.getTime())}
                        </div>
                        <div class="mb-1 p-1 text-muted rounded shadow-sm d-inline-block">
                            <Fa icon={faFlagCheckered} /> Will end on {timestampToISODate(newScheduleEndDate.getTime())}
                        </div>
                    </div>
                    <div class="me-3 w-25">
                        <div class="mb-3">
                            <div class="form-label">Assignee</div>
                            <Select
                                --item-height="auto"
                                --item-line-height="auto"
                                items={prepareUsers(users)}
                                itemFilter={filterUser}
                                placeholder="Select assignee"
                                on:select={handleAssigneeSelect}
                            >
                                <div slot="item" let:item let:index>
                                    <User {item} />
                                </div>
                            </Select>
                        </div>
                    </div>
                </div>
                <div class="mb-3 w-100">
                    <button
                        class="btn btn-success w-100"
                        onclick={submitNewSchedule}>Create</button
                    >
                </div>
            </div>
        {:else}
            <div class="col d-flex align-items-center justify-content-center">
                <div class="spinner-border me-3 text-muted"></div>
                <div class="display-6 text-muted">Fetching users...</div>
            </div>
        {/if}
    </div>
</div>

<style>

</style>
