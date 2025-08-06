<script lang="ts">
    import { createEventDispatcher, onMount } from "svelte";
    import { fly } from "svelte/transition";
    import Fa from "svelte-fa";
    import { faTimes } from "@fortawesome/free-solid-svg-icons";
    let { message = {
        id: "-1",
        type: "error",
        message: "No error",
    } } = $props();
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

<div class="argus-message m-4 {classMap[message.type]} text-light" in:fly="{{x: -300, duration: 1000}}" out:fly="{{x: -300, duration: 1000}}">
    <div class="d-flex flex-column position-relative">
        <h4 class="d-flex align-items-center">
            <span class="me-4">{typeMap[message.type]}</span>
            <button
                onclick={handleClose}
                class="ms-auto btn btn-sm btn-light text-danger"
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

<style>
    .text-sm {
        font-size: 0.75em;
    }
    .argus-message {
        padding: 24px;
        border-radius: 8px;
        margin-bottom: 10px;
    }
</style>
