<!-- @migration-task Error while migrating Svelte code: can't migrate `let deleting = false;` to `$state` because there's a variable named state.
     Rename the variable and try again or migrate by hand. -->
<script>
    import Fa from "svelte-fa";
    import {
        faTrashAlt,
        faEdit,
        faCheck,
        faTimes,
        faExternalLinkSquareAlt,
    } from "@fortawesome/free-solid-svg-icons";
    import Select from "svelte-select";
    import User from "../Profile/User.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { stateEncoder } from "../Common/StateManagement";
    import { createEventDispatcher, onMount } from "svelte";
    export let scheduleData = {};
    export let releaseData = {};
    export let users = {};
    export let absolute = true;
    let deleting = false;
    let reassigning = false;
    let updating = false;
    let reassigned = [];
    const dispatch = createEventDispatcher();
    let state = "e30";
    const getPicture = function (id) {
        return id ? `/storage/picture/${id}` : "/s/no-user-picture.png";
    };

    const prepareState = function () {
        return scheduleData.tests.reduce((acc, scheduledTest) => {
            let [group, test] = scheduledTest.split("/");
            let release = releaseData.release.name;
            acc[`${release}/${group}/${test}`] = {
                release: release,
                group: group,
                test: test,
            };
            return acc;
        }, {});
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

    const handleReassign = async function () {
        updating = true;
        if (!reassigned || reassigned.length == 0) {
            sendMessage("error", "Assignee list is empty!", "Schedule::handleReassign");
            updating = false;
            return;
        }
        try {
            let apiResponse = await fetch(
                "/api/v1/release/schedules/assignee/update",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        releaseId: releaseData.release.id,
                        scheduleId: scheduleData.id,
                        newAssignees: reassigned.map((v) => v.value),
                    }),
                }
            );
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                reassigning = false;
                reassigned = [];
                scheduleData.assignees = apiJson.response.newAssignees;
                scheduleData = scheduleData;
                dispatch("refreshSchedules");
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to reassign the schedule.\nAPI Response: ${error.response.arguments[0]}`,
                    "Schedule::handleReassign"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during schedule reassignment",
                    "Schedule::handleReassign"
                );
            }
        } finally {
            updating = false;
        }
    };

    const handleScheduleDelete = function (e) {
        e.stopPropagation();
        deleting = true;
        dispatch("deleteSchedule", {
            id: scheduleData.id,
        });
    };

    onMount(() => {
        state = stateEncoder(prepareState());
    });
</script>

<div class="card-schedule card-popout" class:position-absolute={absolute}>

    <div
        class="border rounded bg-white shadow-sm mb-3 p-3 d-flex flex-column align-items-start justify-content-center"
    >
        <div class="text-end w-100">
            <button class="btn btn-sm btn-dark" on:click={
                (e) => {
                    e.stopPropagation();
                    dispatch("closeSchedule", scheduleData);
                }
            }>
                <Fa icon={faTimes}/>
            </button>
        </div>
        <div class="d-flex w-100 mb-3">
            <div
                class="me-3"
                class:w-25={scheduleData.tests.length > 0}
                class:w-75={scheduleData.tests.length == 0}
                class:d-none={scheduleData.groups.length == 0}
            >
                <h6>Groups</h6>
                <ul class="list-group list-schedule">
                    {#each scheduleData?.groups ?? [] as group}
                        <li class="list-group-item d-flex align-items-center">
                            <div>
                                {(releaseData.groups.find(
                                    (val) => val.id == group
                                )?.pretty_name || releaseData.groups.find(
                                    (val) => val.id == group
                                )?.name) ?? `[Deleted: ${group}]`}
                            </div>
                        </li>
                    {/each}
                </ul>
            </div>
            <div
                class="me-3"
                class:w-25={scheduleData.groups.length > 0}
                class:w-75={scheduleData.groups.length == 0}
                class:d-none={scheduleData.tests.length == 0}
            >
                <h6>Tests</h6>
                <ul class="list-group list-schedule">
                    {#each scheduleData.tests as test}
                        <li class="list-group-item d-flex align-items-center">
                            <div>{releaseData.tests.find(
                                (val) => val.id == test
                            )?.name ?? `[Deleted: ${test}]`}</div>
                        </li>
                    {/each}
                </ul>
            </div>
            {#if releaseData.release.perpetual}
                <div class="me-3 w-25">
                    <h6>Date</h6>
                    <div>
                        From:
                        <div class="text-muted font-small">
                            {new Date(
                                scheduleData.period_start
                            ).toLocaleDateString()}
                        </div>
                    </div>
                    <div>
                        To:
                        <div class="text-muted font-small">
                            {new Date(
                                scheduleData.period_end
                            ).toLocaleDateString()}
                        </div>
                    </div>
                </div>
            {/if}
        </div>
        {#if scheduleData.tag}
            <div class="me-3 w-100">
                Comment
                <p class="border rounded p-2 mb-3">
                    {scheduleData.tag}
                </p>
            </div>
        {/if}
        <div class="me-3 w-100">
            {#if !reassigning}
                <h6>Assignees</h6>
                <div class="d-flex align-items-top mb-3">
                    <ul class="list-group flex-fill">
                        {#each scheduleData.assignees as assignee}
                            <li
                                class="list-group-item d-flex align-items-center"
                            >
                                <div class="me-2">
                                    <img
                                        class="img-profile"
                                        src={getPicture(
                                            users[assignee]?.picture_id
                                        )}
                                        alt=""
                                    />
                                </div>
                                <div>{users[assignee]?.username}</div>
                            </li>
                        {/each}
                    </ul>
                    <button
                        class="btn btn-dark ms-1"
                        on:click={() => (reassigning = true)}
                    >
                        <Fa icon={faEdit} />
                    </button>
                </div>
            {:else}
                <div class="d-flex align-items-top mb-3">
                    {#if !updating}
                        <div class="flex-fill">
                            <Select
                                --item-height="auto"
                                --item-line-height="auto"
                                items={prepareUsers(users)}
                                bind:value={reassigned}
                                multiple={true}
                                placeholder="Re-assign assignees"
                            >
                                <div slot="item" let:item let:index>
                                    <User {item} />
                                </div>
                            </Select>
                        </div>
                        <div class="ms-1">
                            <button
                                class="btn btn-dark"
                                on:click={handleReassign}
                            >
                                <Fa icon={faCheck} />
                            </button>
                        </div>
                    {:else}
                        <div class="flex-fill">
                            <span class="spinner-border spinner-border-sm" /> Reassigning...
                        </div>
                    {/if}
                </div>
            {/if}
            <div class="text-end">
                <a
                    class="btn btn-primary"
                    href="/workspace?{state}"
                >
                    <Fa icon={faExternalLinkSquareAlt} />
                </a>
                {#if deleting}
                    <button
                        class="btn btn-sm btn-danger"
                        title="Please wait..."
                        type="button"
                    >
                        <span class="spinner-border spinner-border-sm" />
                    </button>
                {:else}
                    <button
                        class="btn btn-danger"
                        title="Delete schedule"
                        type="button"
                        data-bs-toggle="modal"
                        data-bs-target="#modalScheduleConfirmDelete-{scheduleData.id}"
                    >
                        <Fa icon={faTrashAlt} />
                    </button>
                {/if}
            </div>
        </div>
    </div>
</div>

<div
    class="modal"
    tabindex="-1"
    id="modalScheduleConfirmDelete-{scheduleData.id}"
>
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Deleting a schedule</h5>
                <button
                    type="button"
                    class="btn-close"
                    data-bs-dismiss="modal"
                    aria-label="Close"
                />
            </div>
            <div class="modal-body">
                <p>Are you sure you want to delete this schedule?</p>
            </div>
            <div class="modal-footer">
                <button
                    type="button"
                    class="btn btn-secondary"
                    data-bs-dismiss="modal">No</button
                >
                <button
                    type="button"
                    class="btn btn-danger"
                    data-bs-dismiss="modal"
                    on:click={handleScheduleDelete}
                >
                    Yes
                </button>
            </div>
        </div>
    </div>
</div>

<style>
    .font-small {
        font-size: 0.9em;
    }
    .img-profile {
        height: 32px;
        border-radius: 50%;
        object-fit: cover;
    }

    .card-schedule {
        width: 512px;
        z-index: 9999;
        top: 100%;
        left: 0px;
        cursor: default;
    }

    .list-schedule {
        height: 256px;
        overflow-y: scroll;
    }
</style>
