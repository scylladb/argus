<script lang="ts">
    import { createEventDispatcher, onMount } from "svelte";
    import Select from "svelte-select";
    import { endDate, startDate, timestampToISODate } from "../Common/DateUtils";
    import User from "../Profile/User.svelte";
    import { faArrowAltCircleRight, faFlagCheckered, faTimes, faTrash } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import { sendMessage } from "../Stores/AlertStore";
    import { filterUser } from "../Common/SelectUtils";
    import ModalWindow from "../Common/ModalWindow.svelte";

    let {
        selectedTests = $bindable([]),
        clickedTests = $bindable({}),
        selectedAssignee = $bindable(),
        releaseData = {},
        plannerData = {},
        users = $bindable({})
    } = $props();
    let oldSchedule;

    export const enterEditMode = function (schedule) {
        newSchedule = Object.assign({}, schedule);
        oldSchedule = schedule;
        users = users;
        mode = "edit";
    };

    export const exitEditMode = function () {
        newSchedule = Object.assign({}, PayloadTemplate);
        selectedTests = [];
        selectedAssignee = undefined;
        oldSchedule = undefined;
        clickedTests = {};
        mode = "create";
    };

    export const getCurrentMode = () => mode;
    export const getCurrentScheduleId = () => newSchedule.id;

    let mode = $state("create"); // create, edit
    let deleting = $state(false);
    let lockButtons = $state(false);

    const getAllComments = function () {
        return plannerData.tests
            .map((test) => {
                return test.comment;
            })
            .filter((comment) => comment);
    };

    const fetchVersions = async function() {
        let response = await fetch(`/api/v1/release/${plannerData.release.id}/versions`);
        if (response.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await response.json();
        if (json.status !== "ok") {
            return Promise.reject(json.exception);
        }

        autocompleteVersions = json.response;
    };

    /**
     *
     * @param {Array<string>} autocompleteList
     */
    const uniqueAutocompleteTokens = function(autocompleteList) {
        return autocompleteList.reduce((acc, val) => {
            if (!acc.includes(val)) {
                acc.push(val);
            }
            return acc;
        }, []);
    };

    let autocompleteVersions = $state([]);
    let autocompleteComments = getAllComments();

    const dispatch = createEventDispatcher();

    const PayloadTemplate = {
        releaseId: releaseData.release.id,
        groups: [],
        tests: [],
        start: startDate(releaseData.release),
        end: endDate(releaseData.release, startDate(releaseData.release)),
        assignees: [],
        tag: "",
    };

    let newSchedule = $state(Object.assign(PayloadTemplate));

    const submitNewSchedule = async function () {
        try {
            lockButtons = true;
            let payload = Object.assign({}, newSchedule);
            payload.start = timestampToISODate(payload.start.getTime());
            payload.end = timestampToISODate(payload.end.getTime());
            payload.assignees = [selectedAssignee?.id || undefined];
            payload.tests = selectedTests.map(v => v.id);
            payload.comments = selectedTests.reduce((acc, val) => {(acc[val.id] = val.comment); return acc;}, {});
            payload.groupIds = selectedTests.reduce((acc, val) => {(acc[val.id] = val.group_id); return acc;}, {});

            let apiResponse = await fetch("/api/v1/release/schedules/submit", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                dispatch("fetchSchedules", true);
                dispatch("fetchPlannerData", true);
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
                console.log(error);
                console.trace();
            }
        } finally {
            lockButtons = false;
        }
    };

    const updateSchedule = async function() {
        try {
            lockButtons = true;
            let apiResponse = await fetch("/api/v1/release/schedules/update", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    release_id: releaseData.release.id,
                    schedule_id: newSchedule.id,
                    assignee: selectedAssignee.id,
                    new_tests: selectedTests.map(v => v.id),
                    old_tests: oldSchedule.tests,
                    comments: selectedTests.reduce((acc, val) => {(acc[val.id] = val.comment); return acc;}, {}),
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                dispatch("fetchSchedules", true);
                dispatch("fetchPlannerData", true);
                exitEditMode();
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to update schedule.\nAPI Response: ${error.response.arguments[0]}`,
                    "ReleasePlanner::deleteSchedule"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during schedule update",
                    "ReleasePlanner::deleteSchedule"
                );
                console.log(error);
                console.trace();
            }
        } finally {
            lockButtons = false;
        }
    };

    const deleteSchedule = async function (scheduleId) {
        try {
            lockButtons = true;
            let apiResponse = await fetch("/api/v1/release/schedules/delete", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    releaseId: releaseData.release.id,
                    scheduleId: scheduleId,
                    deleteComments: true,
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                dispatch("fetchSchedules", true);
                dispatch("fetchPlannerData", true);
                exitEditMode();
            } else {
                throw apiJson;
            }
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
        } finally {
            deleting = false;
            lockButtons = false;
        }
    };

    const handleTestsClear = function () {
        clickedTests = {};
        selectedTests = [];
    };

    onMount(() => {
        fetchVersions();
    });
</script>
{#if deleting}
    <ModalWindow on:modalClose={() => deleting = false}>
        {#snippet title()}
                <span >Deleting schedule</span>
            {/snippet}
        {#snippet body()}
                <div >
                <div>Are you sure you want to delete this schedule?</div>
                {#if lockButtons}
                    <div><span class="spinner-border spinner-border-sm"></span> Working...</div>
                {/if}
                <div class="text-end">
                    <button class="btn btn-danger" disabled={lockButtons} onclick={() => deleteSchedule(newSchedule.id)}>Confirm</button>
                    <button class="btn btn-secondary" disabled={lockButtons} onclick={() => deleting = false}>Cancel</button>
                </div>
            </div>
            {/snippet}
    </ModalWindow>
{/if}
<div class="my-2 bg-light-one p-2 rounded shadow-sm">
    {#if releaseData.release.perpetual}
        <div>
            <div class="rounded p-2 border-warning border bg-warning bg-opacity-50">
                <b>Important:</b> Test schedules are only valid for this week!
            </div>
        </div>
    {/if}
    {#if Object.values(users).length > 0}
        {#if mode == "create"}
            <div class="mb-2 w-100">
                <button class="btn btn-success w-100" onclick={submitNewSchedule} disabled={lockButtons}>{#if lockButtons}
                    <span class="spinner-border spinner-border-sm"></span>
                {/if} Create</button>
            </div>
        {:else if mode == "edit"}
            <div class="mb-2 btn-group w-100">
                <button class="btn btn-warning" disabled={lockButtons} onclick={() => updateSchedule()}>{#if lockButtons}
                    <span class="spinner-border spinner-border-sm"></span>
                {/if} Update</button>
                <button class="btn btn-secondary" disabled={lockButtons} onclick={() => exitEditMode()}>Cancel</button>
                <button class="btn btn-danger" disabled={lockButtons} onclick={() => deleting = true}>Delete</button>
            </div>
        {/if}
        <div class="d-flex mb-1">
            <div class="mb-1 w-100 flex-fill">
                <label for="newScheduleComment" class="form-label">Plan Comment</label>
                <textarea
                    class="form-control w-100"
                    id="newScheduleComment"
                    style="resize: none;"
                    bind:value={newSchedule.tag}
></textarea>
            </div>
        </div>
        <div class="mb-2">
            {#if releaseData.release.perpetual}
                <div>
                    <div class="mb-1">Timing</div>
                    <div class="mb-1 p-1 text-muted rounded shadow-sm d-inline-block">
                        <Fa icon={faArrowAltCircleRight} /> Will start on {timestampToISODate(
                            newSchedule.start.getTime()
                        )}
                    </div>
                    <div class="mb-1 p-1 text-muted rounded shadow-sm d-inline-block">
                        <Fa icon={faFlagCheckered} /> Will end on {timestampToISODate(
                            newSchedule.end.getTime()
                        )}
                    </div>
                </div>
            {/if}
        </div>
        <div>
            <div class="mb-3">
                <div class="form-label">Assignee</div>
                <Select
                    --item-height="auto"
                    --item-line-height="auto"
                    items={Object.values(users)}
                    itemId="id"
                    label="full_name"
                    itemFilter={filterUser}
                    placeholder="Select assignee"
                    bind:value={selectedAssignee}
                >
                    <div slot="item" let:item let:index>
                        <User {item} />
                    </div>
                </Select>
            </div>
        </div>
        <div>
            <div class="mb-3">
                <datalist id="comment-autocomplete">
                    {#each uniqueAutocompleteTokens([...autocompleteVersions, ...autocompleteComments]) as val}
                        <option value="{val}"></option>
                    {/each}
                </datalist>
                {#if selectedTests.length > 0}
                        <div class="w-100 mb-1">
                            <button class="w-100 btn btn-danger" disabled={lockButtons} onclick={() => handleTestsClear()}><Fa icon={faTrash}/> Clear All</button>
                        </div>
                {/if}
                <ul class="list-group">
                    {#each selectedTests as test (test.id)}
                        <li class="list-group-item">
                            <div class="d-flex align-items-center mb-1">
                                <div>{test.name}</div>
                                <div class="ms-auto">
                                    <button
                                        class="btn btn-dark btn-sm"
                                        disabled={lockButtons}
                                        onclick={() => {
                                            selectedTests = selectedTests.filter(v => v.id != test.id);
                                            clickedTests[test.id] = false;
                                        }}
                                    >
                                        <Fa icon={faTimes}/>
                                    </button>
                                </div>
                            </div>
                            <div>
                                <div class="input-group">
                                    <input type="text" class="form-control" placeholder="Comment" list="comment-autocomplete" bind:value={test.comment}>
                                    <button class="btn btn-secondary" disabled={lockButtons} onclick={() => selectedTests.forEach(v => {
                                        v.comment = test.comment;
                                        selectedTests = selectedTests;
                                    })}>All</button>
                                </div>
                            </div>
                        </li>
                    {:else}
                        <div class="text-muted p-2 text-center">Select tests by clicking on them on the left</div>
                    {/each}
                </ul>
            </div>
        </div>
    {:else}
        <div class="col d-flex align-items-center justify-content-center">
            <div class="spinner-border me-3 text-muted"></div>
            <div class="display-6 text-muted">Fetching users...</div>
        </div>
    {/if}
</div>
