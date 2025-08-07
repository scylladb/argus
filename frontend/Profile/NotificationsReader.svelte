<script lang="ts">
    import { onMount } from "svelte";
    import Fa from "svelte-fa";
    import { faArrowRight, faArrowLeft } from "@fortawesome/free-solid-svg-icons";
    import humanizeDuration from "humanize-duration";
    import { apiMethodCall } from "../Common/ApiUtils";
    import {
        ArgusShortSummary,
        NotificationsState
    } from "../Common/ArgusNotification";
    import type { ArgusShortSummaryJSON } from "../Common/ArgusNotification";
    import { userList as UserStore } from "../Stores/UserlistSubscriber";
    import Notification from "./Notification.svelte";
    import NotificationSender from "./NotificationSender.svelte";
    let users: UserList = $derived($UserStore);

    let notifications: Array<ArgusShortSummary> = $state([]);
    let selectedNotification: ArgusShortSummary | null = $state();
    let prevPage: string = $state("");
    let nextPage: string = $state("");
    let perPageLimit = 10;

    interface UserList {
        [key: string]: Object
    }

    const fetchNotifications = async function () {
        let params = new URLSearchParams({
            afterId: nextPage,
            limit: perPageLimit.toString(),
        }).toString();
        let result = await apiMethodCall(
            "/api/v1/notifications/summary?" + params,
            undefined,
            "GET"
        );
        if (result.status === "ok") {
            notifications = result.response.map(
                (json: ArgusShortSummaryJSON) => {
                    return ArgusShortSummary.from_json(json);
                }
            );
        }
    };

    onMount(() => {
        fetchNotifications();
    });
</script>

{#if users && Object.keys(users).length > 0}
    <div class="my-2 rounded overflow-hidden shadow min-vh-100 bg-light-two">
        <div class="row min-vh-100 overflow-hidden">
            <div class="col-4 bg-light-three p-0 border-end border-light">
                <ul class="list-group list-group-flush">
                    {#each notifications as n (n.id)}
                        <li
                            class="list-group-item"
                            role=button
                            class:active={n.id == selectedNotification?.id}
                            onclick={() => {
                                n.state = NotificationsState.READ
                                selectedNotification = null;
                                setTimeout(() => {
                                    selectedNotification = n;
                                }, 100);
                            }}
                        >
                            <div class="d-flex align-items-top">
                                <NotificationSender user={users[n.sender]} />
                                <div class="ms-auto text-muted fs-6">
                                    { humanizeDuration((new Date()).getTime() - n.date.getTime(), {
                                        round: true,
                                        units: ["y", "mo", "w", "d", "h", "m"],
                                        largest: 1,
                                    }) } ago
                                </div>
                            </div>
                            <div class="notification-title" class:fw-bold={n.state == NotificationsState.UNREAD}>
                                {n.title}
                            </div>
                        </li>
                    {:else}
                        <li class="list-group-item text-muted text-center">
                            No notifications.
                        </li>
                    {/each}
                </ul>
                {#if notifications.length > 0 && perPageLimit == notifications.length}
                    <div class="d-flex justify-content-center align-items-between p-4">
                        <button
                        class="btn btn-primary"
                        onclick={() => {
                            nextPage = prevPage;
                            fetchNotifications();
                            }}
                        >
                            <Fa icon={faArrowLeft} />
                        </button>
                        <button
                            class="ms-auto btn btn-primary"
                            onclick={() => {
                                prevPage = notifications[0].id;
                                nextPage = notifications[notifications.length - 1].id;
                                fetchNotifications();
                            }}
                        >
                            <Fa icon={faArrowRight} />
                        </button>
                    </div>
                {/if}
            </div>
            <div class="col-8 bg-white shadow-sm">
                {#if selectedNotification}
                    <Notification summary={selectedNotification}/>
                {:else}
                    <div class="text-muted text-center">No message selected.</div>
                {/if}
            </div>
        </div>
    </div>
{/if}


<style>
    .notification-title {
        font-weight: 500;
        font-size: 12pt;
        margin-left: 8px;
    }
</style>
