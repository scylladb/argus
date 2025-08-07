<script>
    import { onDestroy, onMount } from "svelte";
    import { apiMethodCall } from "../Common/ApiUtils";
    let unreadCount = $state(0);
    let notificationCheckInterval;
    const getUnreadNotificationsCount = async function () {
        let result = await apiMethodCall("/api/v1/notifications/get_unread", undefined, "GET");
        if (result.status === "ok") {
            unreadCount = result.response;
        }
    };

    onMount(() => {
        getUnreadNotificationsCount();
        notificationCheckInterval = setInterval(() => {
            getUnreadNotificationsCount();
        }, 60 * 1000);
    });

    onDestroy(() => {
        clearInterval(notificationCheckInterval);
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
