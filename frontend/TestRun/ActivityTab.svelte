<script lang="ts">
    import { run } from 'svelte/legacy';

    import { onMount } from "svelte";
    import { userList } from "../Stores/UserlistSubscriber";

    let users = $state({});
    run(() => {
        users = $userList;
    });
    let fetching = $state(true);
    interface Props {
        id?: string;
    }

    let { id = "" }: Props = $props();
    let activity = $state({
        events: {},
        raw_events: {},
        test_run_id: "",
    });

    const getPictureForId = function (id) {
        let picture_id = users[id]?.picture_id;
        return picture_id
            ? `/storage/picture/${picture_id}`
            : "/s/no-user-picture.png";
    };

    const fetchActivity = async function () {
        fetching = true;
        try {
            let apiResponse = await fetch(`/api/v1/run/${id}/activity`);
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
                onclick={fetchActivity}
            />
        </div>
    </div>
    {#each activity.raw_events as event}
        <div class="row p-0 m-0">
            <div class="col p-0 m-0">
                <div class="card-body border-bottom">
                    <p class="card-text"><img
                        class="img-profile"
                        src={getPictureForId(event.user_id)}
                        alt=""
                    /> {@html activity.events[event.id]}
                    <small class="text-muted"
                        >{new Date(
                            event.created_at
                        ).toISOString()}</small
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
