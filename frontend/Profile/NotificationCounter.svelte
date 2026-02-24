<script>
    import { onDestroy, onMount } from "svelte";
    import { apiMethodCall } from "../Common/ApiUtils";

    const POLL_INTERVAL_MS = 5 * 60 * 1000;
    const BROADCAST_CHANNEL_NAME = "argus_notifications";
    const LOCK_NAME = "argus_notification_leader";

    let unreadCount = $state(0);
    let notificationCheckInterval;
    /** @type {BroadcastChannel} */
    let channel;

    const fetchAndBroadcast = async function () {
        let result = await apiMethodCall("/api/v1/notifications/get_unread", undefined, "GET");
        if (result.status === "ok") {
            unreadCount = result.response;
            channel.postMessage({ unreadCount: result.response });
        }
    };

    const startLeaderPolling = function () {
        navigator.locks.request(LOCK_NAME, async () => {
            await fetchAndBroadcast();
            await new Promise((resolve) => {
                notificationCheckInterval = setInterval(fetchAndBroadcast, POLL_INTERVAL_MS);
                window.addEventListener("beforeunload", resolve, { once: true });
            });
        });
    };

    onMount(() => {
        channel = new BroadcastChannel(BROADCAST_CHANNEL_NAME);
        channel.addEventListener("message", (event) => {
            if (typeof event.data?.unreadCount === "number") {
                unreadCount = event.data.unreadCount;
            }
        });
        startLeaderPolling();
    });

    onDestroy(() => {
        clearInterval(notificationCheckInterval);
        channel?.close();
    });
</script>

{#if unreadCount > 0}
    <div class="notification-counter bg-danger shadow-sm text-light rounded-pill d-flex align-items-center justify-content-center">
        <div>
            {unreadCount}
        </div>
    </div>
{/if}


<style>
    .notification-counter {
        padding: 0px 4px;
        height: 24px;
        font-size: 0.75em;
    }
</style>
