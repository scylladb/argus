<script>
    import { onMount } from "svelte";
    import { userList } from "./UserlistSubscriber.js";

    export const eventTypes = {
        AssigneeChanged: "ARGUS_ASSIGNEE_CHANGE",
        TestRunStatusChanged: "ARGUS_TEST_RUN_STATUS_CHANGE",
        TestRunCommentPosted: "ARGUS_TEST_RUN_COMMENT_POSTED",
    };

    let users = {};
    $: users = $userList;
    let fetching = true;
    let eventLimit = 10;
    export let releaseName = undefined;
    let activity = {
        events: {},
        raw_events: {},
        release_name: "",
    };

    const getPictureForId = function (id) {
        let picture_id = users[id]?.picture_id;
        return picture_id
            ? `/storage/picture/${picture_id}`
            : "/static/no-user-picture.png";
    };

    const fetchActivity = async function () {
        fetching = true;
        try {
            let apiResponse = await fetch("/api/v1/release/activity", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    release_name: releaseName,
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                activity = apiJson.response;
                fetching = false;
                console.log(activity);
            }
        } catch (error) {
            console.log(error);
        }
    };

    onMount(() => {
        fetchActivity();
    });
</script>

{#if Object.keys(users).length > 0}
    <div class="row p-0 m-0 justify-content-end">
        <div class="col-1 p-1 mb-2">
            <input
                class="btn btn-secondary"
                type="button"
                value="Refresh"
                disabled={fetching}
                on:click={fetchActivity}
            />
        </div>
    </div>
    {#each activity.raw_events.slice(0, eventLimit) as event}
        <div class="row p-0 m-0">
            <div class="col p-0 m-0">
                <div class="card-body border-bottom">
                    <div class="card-subtitle text-muted"><a class="link-secondary" href="/test_run/{event.run_id}">[Test Run]</a></div>
                    <p class="card-text"><img
                        class="img-profile"
                        src={getPictureForId(event.user_id)}
                        alt=""
                    /> {activity.events[event.id]}
                    <small class="text-muted"
                        >{new Date(
                            event.created_at
                        ).toLocaleString()}</small
                    >
                        </p>
                </div>
            </div>
        </div>
    {:else}
        <div class="row">
            <div class="col text-center p-1 text-muted">No events yet.</div>
        </div>
    {/each}
{:else}
    loading...
{/if}

<style>
    .img-profile {
        height: 24px;
        border-radius: 50%;
        object-fit: cover;
    }
</style>
