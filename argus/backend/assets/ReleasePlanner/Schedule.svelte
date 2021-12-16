<script>
    import Fa from "svelte-fa";
    import {
        faCircle,
        faTrashAlt,
        faExternalLinkSquareAlt,
    } from "@fortawesome/free-solid-svg-icons";
    import { StatusCSSClassMap } from "../Common/TestStatus";
    import { createEventDispatcher } from "svelte";
    import { Base64 } from "js-base64";
    export let scheduleData = {};
    export let releaseData = {};
    export let users = {};
    export let absolute = true;
    const dispatch = createEventDispatcher();
    let state = "e30";
    const getPicture = function (id) {
        return id ? `/storage/picture/${id}` : "/static/no-user-picture.png";
    };

    const handleScheduleDelete = function () {
        dispatch("deleteSchedule", {
            id: scheduleData.schedule_id,
        });
    };
</script>

<div class="card-schedule card-popout" class:position-absolute={absolute}>
    <div
        class="border rounded bg-white shadow-sm mb-3 p-3 d-flex flex-column align-items-start justify-content-center"
    >
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
                                {releaseData.groups.find((val) => val.name == group)
                                    .pretty_name}
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
                            <div>{test}</div>
                        </li>
                    {/each}
                </ul>
            </div>
            <div class="me-3 w-25">
                <h6>Date</h6>
                <div>
                    From:
                    <div class="text-muted font-small">
                        {new Date(scheduleData.period_start).toLocaleDateString()}
                    </div>
                </div>
                <div>
                    To:
                    <div class="text-muted font-small">
                        {new Date(scheduleData.period_end).toLocaleDateString()}
                    </div>
                </div>
            </div>
        </div>
        <div class="me-3 w-100">
            <h6>Assignees</h6>
            <ul class="list-group mb-3">
                {#each scheduleData.assignees as assignee}
                    <li class="list-group-item d-flex align-items-center">
                        <div class="me-2">
                            <img
                                class="img-profile"
                                src={getPicture(users[assignee]?.picture_id)}
                                alt=""
                            />
                        </div>
                        <div>{users[assignee]?.username}</div>
                    </li>
                {/each}
            </ul>
            <div class="text-end">
                <a
                    class="btn btn-primary"
                    href="/run_dashboard?state={state}"
                    target="_blank"
                >
                    <Fa icon={faExternalLinkSquareAlt} />
                </a>
                <button class="btn btn-danger" on:click={handleScheduleDelete}>
                    <Fa icon={faTrashAlt} />
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
        height: 576px;
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
