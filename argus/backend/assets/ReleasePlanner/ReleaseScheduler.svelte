<script>
    import { onMount } from "svelte";
    import * as chrono from "chrono-node";
    import Select from "svelte-select";
    import User from "../Profile/User.svelte";
    import ScheduleTable from "./ScheduleTable.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    import { sendMessage } from "../Stores/AlertStore";
    export let releaseData = {};
    export let schedules = [];
    let users = {};
    $: users = $userList;
    let selectedGroups = [];
    let selectedTests = [];

    const PayloadTemplate = {
        release: releaseData.release.name,
        groups: [],
        tests: [],
        start: undefined,
        end: undefined,
        assignees: [],
    };

    const generateNewScheduleDate = function(today = new Date()) {
        let monday = chrono.parseDate("This Monday", new Date(today));
        return monday.toISOString().split("T").shift();
    }

    const generateEndDate = function(startDate) {
        let start = new Date(startDate);
        let end = chrono.parseDate("Next Sunday at 23:59", start);
        return end;
    };

    const handleDateChange = function(value) {
        newScheduleDate = generateNewScheduleDate(value);
        newScheduleEndDate = generateEndDate(newScheduleDate);

        newSchedule.start = new Date(newScheduleDate).toISOString().split(".").shift();
        newSchedule.end = newScheduleEndDate.toISOString().split(".").shift();
    }

    let newSchedule = Object.assign(PayloadTemplate);
    let newScheduleDate = generateNewScheduleDate();
    let newScheduleEndDate = generateEndDate(newScheduleDate);

    const fetchSchedules = async function () {
        try {
            let apiResponse = await fetch("/api/v1/release/schedules", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    release: releaseData.release.name,
                }),
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
                    `Unable to fetch schedules.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during schedule fetch"
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
                    `Unable to submit schedule.\nAPI Response: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during schedule submission"
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
                    release: releaseData.release.name,
                    schedule_id: scheduleId,
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
                    `Unable to delete schedule.\nAPI Response: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during schedule deletion"
                );
            }
        }
    };

    const extractGroups = function (releaseData) {
        return Object.values(releaseData.groups).map((val) => {
            return {
                label: val.pretty_name,
                value: val.name,
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
        if (selectedGroups.findIndex(val => val.value == data.group.name) == -1) {
            selectedGroups.push({ label: data.group.pretty_name, value: data.group.name });
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
    }

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
        newSchedule.assignees =
            e.detail?.map((val) => {
                return val.value;
            }) ?? [];
        newSchedule = newSchedule;
    };

    onMount(() => {
        fetchSchedules();
    });
</script>

<div class="container-fluid border rounded bg-white my-3 min-vh-100 shadow-sm">
    <div class="row">
        <div class="p-2 display-6">{releaseData.release.name}</div>
    </div>
    <div class="row">
        {#if schedules.length > 0 && Object.values(users).length > 0}
            <ScheduleTable {releaseData} {users} {schedules} on:cellClick={handleCellClick} on:deleteSchedule={deleteSchedule} on:clearGroups={handleClearGroups}/>
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
                                isMulti={true}
                                placeholder="Select groups"
                                on:select={handleGroupSelect}
                                bind:value={selectedGroups}
                            />
                        </div>
                        <div class="mb-3 d-none">
                            <div class="form-label">Tests</div>
                            <Select
                                items={extractTests(releaseData)}
                                isMulti={true}
                                placeholder="Select tests"
                                bind:value={selectedTests}
                                on:select={handleTestSelect}
                            />
                        </div>
                    </div>
                    <div class="me-3 w-25">
                        <div class="mb-3">
                            <label
                                for="newScheduleTimestampStart"
                                class="form-label">From</label
                            >
                            <input
                                type="date"
                                id="newScheduleTimestampStart"
                                bind:value={newScheduleDate}
                                class="form-control"
                                on:change={(e) => handleDateChange(e.target.value)}
                            />
                        </div>
                        <div class="mb-3 text-muted">
                            Will end on {newScheduleEndDate.toLocaleDateString('en-CA', { timeZone: 'UTC' })}
                        </div>
                    </div>
                    <div class="me-3 w-25">
                        <div class="mb-3">
                            <div class="form-label">Assignees</div>
                            <Select
                                Item={User}
                                items={prepareUsers(users)}
                                isMulti={true}
                                placeholder="Select assignees"
                                on:select={handleAssigneeSelect}
                            />
                        </div>
                    </div>
                </div>
                <div class="mb-3 w-100">
                    <button
                        class="btn btn-success w-100"
                        on:click={submitNewSchedule}>Create</button
                    >
                </div>
            </div>
        {:else}
            <div class="col d-flex align-items-center justify-content-center">
                <div class="spinner-border me-3 text-muted" />
                <div class="display-6 text-muted">Fetching users...</div>
            </div>
        {/if}
    </div>
</div>

<style>

</style>
