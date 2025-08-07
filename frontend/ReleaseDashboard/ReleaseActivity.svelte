<script lang="ts">
    import { run } from 'svelte/legacy';

    import { onMount } from "svelte";
    import { userList } from "../Stores/UserlistSubscriber.js";

    export const eventTypes = {
        AssigneeChanged: "ARGUS_ASSIGNEE_CHANGE",
        TestRunStatusChanged: "ARGUS_TEST_RUN_STATUS_CHANGE",
        TestRunCommentPosted: "ARGUS_TEST_RUN_COMMENT_POSTED",
    };

    let users = $state({});
    run(() => {
        users = $userList;
    });
    let fetching = $state(true);
    let eventLimit = $state(10);
    let { releaseName = undefined } = $props();
    let activity = $state({
        events: {},
        raw_events: [],
        release_name: "",
    });

    const getPictureForId = function (id: string) {
        let picture_id = users[id]?.picture_id;
        return picture_id
            ? `/storage/picture/${picture_id}`
            : "/s/no-user-picture.png";
    };

    const reverseArray = function (array: any[]) {
        let arrayCopy = Array.from(array);
        arrayCopy.reverse();
        return arrayCopy;
    };

    const fetchActivity = async function () {
        fetching = true;
        try {
            let params = new URLSearchParams({
                releaseName: releaseName,
            }).toString();
            let apiResponse = await fetch("/api/v1/release/activity?" + params);
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                activity = apiJson.response;
                fetching = false;
            }
        } catch (error) {
            console.log(error);
        }
    };

    onMount(() => {
        fetchActivity();
    });
</script>

<div class="accordion" id="accordionReleaseActivity">
    <div class="accordion-item">
        <h2 class="accordion-header" id="headingReleaseActivity">
            <button
                class="accordion-button collapsed"
                data-bs-toggle="collapse"
                data-bs-target="#collapseReleaseActivity"
                >Activity</button
            >
        </h2>
        <div class="accordion-collapse collapse" id="collapseReleaseActivity">
            {#if Object.keys(users).length > 0}
                <div class="container-fluid">
                    <div class="row justify-content-end">
                        <div class="col-4 p-1 mb-2 text-end">
                            <div class="btn-group">
                                <input
                                    class="btn btn-secondary"
                                    type="button"
                                    value="Refresh"
                                    disabled={fetching}
                                    onclick={fetchActivity}
                                />
                                <input
                                    class="btn btn-secondary"
                                    type="button"
                                    value="More"
                                    onclick={() => {
                                        eventLimit += 10;
                                    }}
                                />
                            </div>
                        </div>
                    </div>
                    {#each reverseArray(activity.raw_events).slice(0, eventLimit) as event}
                        <div class="row border rounded m-2 p-2">
                            <div class="col hstack">
                                <div class="me-2">
                                    <img
                                        class="img-profile"
                                        src={getPictureForId(event.user_id)}
                                        alt=""
                                    />
                                    {activity.events[event.id]}
                                </div>
                                <div class="ms-auto text-muted">
                                    {new Date(
                                        event.created_at
                                    ).toISOString()}
                                </div>
                                <div class="ms-2 text-muted">
                                    <a
                                        class="link-secondary"
                                        href="/test_run/{event.run_id}">Run</a
                                    >
                                </div>
                            </div>
                        </div>
                    {:else}
                        <div class="row">
                            <div class="col text-center p-1 text-muted">
                                No events yet.
                            </div>
                        </div>
                    {/each}
                </div>
            {:else}
                loading...
            {/if}
        </div>
    </div>
</div>

<style>
    .img-profile {
        height: 24px;
        border-radius: 50%;
        object-fit: cover;
    }
</style>
