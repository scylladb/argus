<script>
    import { onMount } from "svelte";
    import Select from "svelte-select";
    import User from "./User.svelte";
    import Schedule from "./Schedule.svelte";
    import ReleaseStats from "./ReleaseStats.svelte";
    import { userList } from "./UserlistSubscriber";
    import { sendMessage } from "./AlertStore";
    export let releaseData = {};
    export let schedules = [];
    let users = {};
    $: users = $userList;
    let releaseStats = {
        created: 0,
        running: 0,
        passed: 0,
        failed: 0,
        aborted: 0,
        lastStatus: "unknown",
        disabled: true,
        groups: {},
        tests: {},
        total: -1,
    };

    const PayloadTemplate = {
        release: releaseData.release.name,
        groups: [],
        tests: [],
        start: undefined,
        end: undefined,
        assignees: [],
    };

    let newSchedule = Object.assign(PayloadTemplate);

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
                fetchSchedules();
                sendMessage("success", "Added new schedule!");
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
                    schedule_id: scheduleId
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                fetchSchedules();
                sendMessage("success", "Schedule deleted, refreshing...");
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

    const handleStatsUpdate = function (e) {
        releaseStats = e.detail.stats;
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
        <ReleaseStats
            releaseName={releaseData.release.name}
            showTestMap={true}
            on:statsUpdate={handleStatsUpdate}
        />
    </div>
    <div class="row">
        {#if Object.values(users).length > 0 && releaseStats.total > 0}
            <div class="col border rounded m-3 p-3">
                <h4 class="mb-3">New schedule</h4>
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
                            />
                        </div>
                        <div class="mb-3">
                            <div class="form-label">Tests</div>
                            <Select
                                items={extractTests(releaseData)}
                                isMulti={true}
                                placeholder="Select tests"
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
                                type="datetime-local"
                                id="newScheduleTimestampStart"
                                value={new Date()}
                                class="form-control"
                                on:change={(e) =>
                                    (newSchedule.start = new Date(
                                        e.target.value
                                    ).getTime())}
                            />
                        </div>
                        <div class="mb-3">
                            <label
                                for="newScheduleTimestampEnd"
                                class="form-label">To</label
                            >
                            <input
                                type="datetime-local"
                                id="newScheduleTimestampEnd"
                                value={new Date()}
                                class="form-control"
                                on:change={(e) =>
                                    (newSchedule.end = new Date(
                                        e.target.value
                                    ).getTime())}
                            />
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
        {:else if releaseStats.total == 0}
            <div class="col">No tests for the release found!</div>
        {:else}
            <div class="col d-flex align-items-center justify-content-center">
                <div class="spinner-border me-3 text-muted" />
                <div class="display-6 text-muted">Fetching release data...</div>
            </div>
        {/if}
    </div>
    <div class="row">
        {#if schedules.length > 0 && Object.values(users).length > 0 && releaseStats.total > 0}
            <h2>Schedules</h2>
            <div id="scheduleContainer" class="container-fluid">
                {#each schedules as schedule (schedule.schedule_id)}
                    <Schedule
                        scheduleData={schedule}
                        {releaseStats}
                        {releaseData}
                        {users}
                        on:deleteSchedule={deleteSchedule}
                    />
                {/each}
            </div>
        {:else}
            <div class="col text-muted text-center my-4">
                Nothing scheduled for this release
            </div>
        {/if}
    </div>
</div>

<style>
    #scheduleContainer {
        height: 1536px;
        overflow-x: visible;
        overflow-y: scroll;
    }
</style>
