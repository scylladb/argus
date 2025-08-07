<script lang="ts">
    import { onMount } from "svelte";
    import { apiMethodCall } from "../Common/ApiUtils";
    import NotificationCommentWrapper from "./NotificationCommentWrapper.svelte";
    import { ArgusNotification, ArgusShortSummary, NotificationSource, NotificationsState } from "../Common/ArgusNotification";
    import NotificationTestRunWrapper from "./NotificationTestRunWrapper.svelte";
    interface Props {
        summary: ArgusShortSummary;
    }

    let { summary }: Props = $props();

    let notification: ArgusNotification = $state();
    let supportDataReady = $state(false);
    let supportData: Object = $state();

    type ComponentSourceType = {
        [key in NotificationSource]: Object
    };

    const ComponentSourceMap: ComponentSourceType = {
        [NotificationSource.Comment]: NotificationCommentWrapper,
        [NotificationSource.TestRun]: NotificationTestRunWrapper,
        [NotificationSource.ViewActionItem]: NotificationTestRunWrapper,
    };

    const SupportDataFetch = {
        [NotificationSource.Comment]: async () => {
            let params = new URLSearchParams({
                commentId: notification.sourceId,
            });
            let result = await apiMethodCall("/api/v1/test_run/comment/get?" + params, undefined, "GET");
            if (result.status === "ok" && result.response) {
                supportDataReady = true;
                supportData = result.response;
            }
        },
        [NotificationSource.TestRun]: async () => {
            return {};
        },
        [NotificationSource.ViewActionItem]: async () => {
            return {};
        },
        [NotificationSource.ViewHighlight]: async () => {
            return {};
        },
    };

    const setNotificationAsRead = async function() {
        let params = {
            id: notification.id,
        };
        let result = await apiMethodCall("/api/v1/notifications/read", params, "POST");
        if (result.status === "ok") {
            //empty
        }
    };

    const fetchNotification = async function() {
        let params = new URLSearchParams({
            id: summary.id,
        });
        let result = await apiMethodCall("/api/v1/notifications/get?" + params, undefined, "GET");
        if (result.status === "ok") {
            notification = ArgusNotification.from_json(result.response);
            (SupportDataFetch[notification.source])();
            if (notification.state == NotificationsState.UNREAD) {
                setNotificationAsRead();
            }
        }
    };

    onMount(() => {
        fetchNotification();
    });
</script>
<div>
    <h1 class="border-bottom border-dark d-inline-block py-3">{summary.title}</h1>
</div>
<div class="text-muted">
    Received: {summary.date}
</div>
{#if notification}
    <div>
        <p class="border-bottom mb-2">
            {@html notification.content}
        </p>
        {#if supportDataReady && supportData}
            {@const SvelteComponent = ComponentSourceMap[notification.source]}
            <div class="support-component-container">
                <SvelteComponent {supportData} />
            </div>
        {/if}
    </div>
{:else}
    <div class="text-muted text-center d-flex align-items-center justify-content-center">
        <span class="spinner-border"></span> <div class="ms-2">Loading content...</div>
    </div>
{/if}
