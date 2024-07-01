<script>
    import { onMount } from "svelte";
    import Select from "svelte-select";
    import Fa from "svelte-fa";
    import { faArrowAltCircleRight, faArrowDown, faCalendar, faFlagCheckered } from "@fortawesome/free-solid-svg-icons";
    import User from "../Profile/User.svelte";
    import ReleasePlanTable from "./ReleasePlanTable.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    import { sendMessage } from "../Stores/AlertStore";
    import {
        startDate,
        endDate,
        timestampToISODate
    } from "../Common/DateUtils";
    import { filterUser } from "../Common/SelectUtils";
    export let releaseData = {};
    export let schedules = [];
    let users = {};
    $: users = $userList;
    let selectedTests = [];
    let selectedAssignee;
    let clickedTests = {};
    let plannerData = {};

    const PayloadTemplate = {
        releaseId: releaseData.release.id,
        groups: [],
        tests: [],
        start: startDate(releaseData.release),
        end: endDate(releaseData.release, startDate(releaseData.release)),
        assignees: [],
        tag: "",
    };

    let newSchedule = Object.assign(PayloadTemplate);

    const fetchPlannerData = async function () {
        try {
            let params = new URLSearchParams({
                releaseId: releaseData.release.id
            }).toString();
            let apiResponse = await fetch("/api/v1/release/planner/data?" + params, {
                method: "GET",
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                plannerData = apiJson.response ?? {};
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to fetch planner data.\nMessage: ${error.response.arguments[0]}`,
                    "ReleasePlanner::fetchPlannerData"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during planner data fetch",
                    "ReleasePlanner::fetchPlannerData"
                );
            }
        }
    };

    const fetchSchedules = async function () {
        try {
            let params = new URLSearchParams({
                releaseId: releaseData.release.id
            });

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
                    "ReleasePlanner::fetchSchedules"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during schedule fetch",
                    "ReleasePlanner::fetchSchedules"
                );
            }
        }
    };

    const submitNewSchedule = async function () {
        try {
            let payload = Object.assign({}, newSchedule);
            payload.start = timestampToISODate(payload.start.getTime());
            payload.end = timestampToISODate(payload.end.getTime());

            let apiResponse = await fetch("/api/v1/release/schedules/submit", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                fetchSchedules();
                handleTestsClear();
                selectedAssignee = undefined;
            } else {
                throw apiJson;
            }
            newSchedule = Object.assign(PayloadTemplate);
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to submit schedule.\nAPI Response: ${error.response.arguments[0]}`,
                    "ReleasePlanner::submitNewSchedule"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during schedule submission",
                    "ReleasePlanner::submitNewSchedule"
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
            } else {
                throw apiJson;
            }
            newSchedule = Object.assign(PayloadTemplate);
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to delete schedule.\nAPI Response: ${error.response.arguments[0]}`,
                    "ReleasePlanner::deleteSchedule"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during schedule deletion",
                    "ReleasePlanner::deleteSchedule"
                );
            }
        }
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

    const extractTests = function (plannerData) {
        if (!plannerData.release) return;
        return Object.values(plannerData.tests)
            .map((val) => {
                return {
                    label: `${val.group_name}/${val.name}`,
                    value: val.id,
                    test: val,
                };
            })
            .sort((a, b) => {
                if (a.label > b.label) {
                    return 1;
                } else if (b.label > a.label) {
                    return -1;
                }
                return 0;
            });
    };

    const handleCellClick = function (e) {
        let data = e.detail;
        let testLabel = `${data.group}/${data.test.name}`;
        if (!selectedTests) {
            selectedTests = [];
        }

        if (selectedTests.findIndex((test) => test.label == testLabel) == -1) {
            selectedTests.push({
                label: testLabel,
                value: data.test.id,
            });
            selectedTests = selectedTests;
            clickedTests[testLabel] = true;
            clickedTests = clickedTests;
            console.log(clickedTests);
            handleTestSelect({
                detail: selectedTests,
            });
        } else {
            clickedTests[testLabel] = false;
            clickedTests = clickedTests;
            selectedTests = selectedTests.filter(
                (test) => test.label != testLabel
            );
            handleTestSelect({
                detail: selectedTests,
            });
        }
    };

    const handleTestsClear = function (e) {
        clickedTests = {};
        selectedTests = [];
        handleTestSelect({
            detail: [],
        });
    };

    const handleTestSelect = function (e) {
        newSchedule.tests =
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
        fetchPlannerData();
    });
</script>

<div class="container-fluid border rounded bg-white my-3 min-vh-100 shadow-sm">
    <div class="row">
        <div class="p-2 display-6">{releaseData.release.name}</div>
        <div>
            <a class="btn btn-primary" href="/release/{releaseData.release.name}/duty"><Fa icon={faCalendar}/> Group Planner</a>
        </div>
    </div>
    <div class="row">
        {#if Object.values(users).length > 0 && plannerData.release}
            <ReleasePlanTable
                {releaseData}
                {users}
                {schedules}
                {plannerData}
                bind:clickedTests
                on:cellClick={handleCellClick}
                on:deleteSchedule={deleteSchedule}
                on:refreshSchedules={() => fetchSchedules()}
            />
        {/if}
    </div>
    {#if releaseData.release.perpetual}
        <div class="row">
            <div class="col p-2">
                <div class="rounded p-2 border-warning border bg-warning bg-opacity-50">
                    <b>Important:</b> Test schedules are only valid for this week!
                </div>
            </div>
        </div>
    {/if}
    <div class="row">
        {#if Object.values(users).length > 0}
            <div class="col border rounded m-3 p-3">
                <h4 class="mb-3">New plan</h4>
                <div class="d-flex align-items-start justify-content-start">
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
                        <div class="mb-3">
                            <label for="newScheduleComment" class="form-label">Comment</label>
                            <textarea
                                class="form-control"
                                id="newScheduleComment"
                                cols="30"
                                rows="5"
                                style="resize: none;"
                                on:keyup={(e) => {newSchedule.tag = e.target.value; newSchedule = newSchedule;}}
                            ></textarea>
                        </div>
                    </div>
                    <div class="me-3 w-50">
                        <div class="mb-3">
                            <div class="form-label">Tests</div>
                            <Select
                                items={extractTests(plannerData)}
                                isMulti={true}
                                placeholder="Select tests"
                                bind:value={selectedTests}
                                on:select={handleTestSelect}
                                on:clear={handleTestsClear}
                            />
                        </div>
                        {#if releaseData.release.perpetual}
                            <div>
                                <div class="mb-1">Timing</div>
                                <div class="mb-1 p-1 text-muted rounded shadow-sm d-inline-block">
                                    <Fa icon={faArrowAltCircleRight} /> Will start on {timestampToISODate(newSchedule.start.getTime())}
                                </div>
                                <div class="mb-1 p-1 text-muted rounded shadow-sm d-inline-block">
                                    <Fa icon={faFlagCheckered} /> Will end on {timestampToISODate(newSchedule.end.getTime())}
                                </div>
                            </div>
                        {/if}
                    </div>
                    <div class="me-3 w-25">
                        <div class="mb-3">
                            <div class="form-label">Assignee</div>
                            <Select
                                Item={User}
                                items={prepareUsers(users)}
                                itemFilter={filterUser}
                                placeholder="Select assignee"
                                bind:value={selectedAssignee}
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

<div
    class:d-none={Object.keys(clickedTests).length == 0}
    class="anchor-down"
>
    <button
        class="btn btn-success"
        on:click={() => {
            window.scrollTo({behavior: "smooth", top: document.body.clientHeight }); 
        }}
    >
        <Fa icon={faArrowDown}/>
    </button>
</div>

<style>
    .anchor-down {
        position: fixed;
        left: 90%;
        top: 90%;

    }
    .anchor-down>button {
        border-radius: 50%;
        width: 64px;
        height: 64px;
    }
</style>
