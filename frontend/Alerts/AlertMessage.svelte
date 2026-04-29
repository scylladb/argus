<script lang="ts">
    import { createEventDispatcher, onMount } from "svelte";
    import { fly } from "svelte/transition";
    import Fa from "svelte-fa";
    import { faTimes } from "@fortawesome/free-solid-svg-icons";
    let { message = {
        id: "-1",
        type: "error",
        message: "No error",
    }, compact = false } = $props();
    const dispatch = createEventDispatcher();

    let messageTimeout;

    const classMap = {
        error: "bg-danger",
        success: "bg-success",
        info: "bg-info"
    };
    const typeMap = {
        error: "An error occurred.",
        success: "Success.",
        info: "Info",
    };
    const handleClose = function () {
        dispatch("deleteMessage", {
            id: message.id,
        });
        if (messageTimeout) clearTimeout(messageTimeout);
    };
    onMount(() => {
        messageTimeout = setTimeout(() => {
            handleClose();
        }, 8000);
    });
</script>

{#if compact}
<div class="argus-message-compact {classMap[message.type]} text-light" in:fly="{{y: 60, duration: 400}}" out:fly="{{y: 60, duration: 300}}">
    <div class="d-flex align-items-center gap-2">
        <span class="badge-dot badge-dot--{message.type}"></span>
        <span class="flex-grow-1 text-truncate compact-body">{message.message}</span>
        <button
            onclick={handleClose}
            class="btn btn-sm btn-link text-light p-0 flex-shrink-0"
            aria-label="Dismiss"
            title="Dismiss"
        >
            <Fa icon={faTimes} />
        </button>
    </div>
</div>
{:else}
<div class="argus-message m-4 {classMap[message.type]} text-light" in:fly="{{x: -300, duration: 1000}}" out:fly="{{x: -300, duration: 1000}}">
    <div class="d-flex flex-column position-relative">
        <h4 class="d-flex align-items-center">
            <span class="me-4">{typeMap[message.type]}</span>
            <button
                onclick={handleClose}
                class="ms-auto btn btn-sm btn-light text-danger"
                aria-label="Dismiss"
                title="Dismiss"
            >
                <Fa icon={faTimes} />
            </button>
        </h4>
        <div>{message.message}</div>
        {#if message.source}
            <div class="text-end text-sm">Source: <span class="fw-bold">{message.source}</span></div>
        {/if}
    </div>
</div>
{/if}

<style>
    .text-sm {
        font-size: 0.75em;
    }
    .argus-message {
        padding: 24px;
        border-radius: 8px;
        margin-bottom: 10px;
    }
    .argus-message-compact {
        padding: 8px 12px;
        border-radius: 6px;
        margin-bottom: 2px;
    }
    .compact-body {
        font-size: 0.85rem;
        line-height: 1.3;
    }
    .badge-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        flex-shrink: 0;
        display: inline-block;
    }
    .badge-dot--error { background-color: #fff; }
    .badge-dot--success { background-color: #fff; }
    .badge-dot--info { background-color: #fff; }
</style>
