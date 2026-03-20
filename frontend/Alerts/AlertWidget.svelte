<script lang="ts">
    import { alertStore } from "../Stores/AlertStore.js";
    import { onDestroy } from "svelte";
    import AlertMessage from "./AlertMessage.svelte";
    import { v4 as uuidv4 } from "uuid";
    let { flashes = [] } = $props();

    let innerWidth = $state(1024);
    let smallScreen = $derived(innerWidth < 768);

    let messages = $state([]);
    let showOldMessages = $state(false);
    let oldMessages = $state([]);
    messages = flashes.map((val) => {
        return {
            id: uuidv4(),
            type: val[0],
            message: val[1],
        };
    });

    const handleCloseEvent = function(e) {
        let message = messages.find(v => v.id == e.detail.id);
        if (message && message.type === "error") {
            oldMessages.push(message);
            oldMessages = oldMessages;
        }
        messages = messages.filter((value) => value.id != e.detail.id);
    };

    const unsubscribe = alertStore.subscribe((value) => {
        if (value?.id) {
            messages = [...messages, value];
        }
    });

    onDestroy(unsubscribe);
</script>

<svelte:window bind:innerWidth />

{#if smallScreen}
<!-- Mobile: fixed bottom bar -->
<div class="alert-mobile-bar" id="alertWidget">
    {#if oldMessages.length > 0}
        <button class="btn btn-danger btn-sm w-100 alert-mobile-errors-btn" onclick={() => (showOldMessages = true)}>
            Show errors ({oldMessages.length})
        </button>
    {/if}
    <div class="alert-mobile-messages">
        {#each messages as message (message.id)}
            <AlertMessage {message} compact={true} on:deleteMessage={handleCloseEvent}/>
        {/each}
    </div>
</div>
{:else}
<!-- Desktop: original top-left overlay -->
<div class="position-absolute top-0 start-0" id="alertWidget">
    {#each messages as message (message.id)}
        <AlertMessage {message} on:deleteMessage={handleCloseEvent}/>
    {/each}
</div>

{#if oldMessages.length > 0}
    <div class="position-fixed" id="alertBucket">
        <button class="btn btn-danger" onclick={() => (showOldMessages = true)}>Show errors</button>
    </div>
{/if}
{/if}

{#if showOldMessages}
    <div class="alert-bucket-modal">
        <div class="d-flex align-items-center justify-content-center p-2 p-md-4" class:h-100={smallScreen}>
            <div class="rounded alert-console-panel p-3 p-md-4" class:alert-console-mobile={smallScreen} class:h-50={!smallScreen} class:w-75={!smallScreen}>
                <div class="mb-2 d-flex border-bottom pb-2">
                    <h5 class="mb-0">Error console</h5>
                    <div class="ms-auto">
                        <button
                            class="btn btn-close"
                            onclick={() => {
                                showOldMessages = false;
                            }}
                        ></button>
                    </div>
                </div>
                <div class="alert-console-body">
                    {#each oldMessages as message}
                        <div class="alert alert-danger">
                            <div>
                                {message?.message || JSON.stringify(message)}
                            </div>
                            {#if message.source}
                                <div class="text-end text-sm">Source: <span class="fw-bold">{message.source}</span></div>
                            {/if}
                        </div>
                    {/each}
                </div>
                <div class="mt-2">
                    <button class="btn btn-primary w-100" onclick={() => {
                        oldMessages = [];
                        showOldMessages = false;
                    }}>Clear all</button>
                </div>
            </div>
        </div>
    </div>
{/if}


<style>
    /* Desktop alert widget */
    :global(#alertWidget:not(.alert-mobile-bar)) {
        width: 512px;
    }

    #alertBucket {
        top: 95%;
        left: 32px;
    }

    .alert-bucket-modal {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        overflow-y: scroll;
        background-color: rgba(0, 0, 0, 0.55);
        z-index: 9999;
    }

    /* Error console panel — light mode */
    .alert-console-panel {
        background-color: #ffffff;
        color: #212529;
    }

    .alert-console-body {
        overflow-y: auto;
        max-height: 60vh;
    }

    /* Mobile error console — near-fullscreen */
    .alert-console-mobile {
        width: 100%;
        height: 90%;
        display: flex;
        flex-direction: column;
    }
    .alert-console-mobile .alert-console-body {
        flex: 1;
        max-height: none;
    }

    /* Mobile bottom bar */
    .alert-mobile-bar {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        z-index: 1050;
        max-height: 30vh;
        overflow-y: auto;
        padding: 4px 6px;
        display: flex;
        flex-direction: column-reverse;
        pointer-events: none;
    }
    .alert-mobile-bar > :global(*) {
        pointer-events: auto;
    }
    .alert-mobile-messages {
        display: flex;
        flex-direction: column;
    }
    .alert-mobile-errors-btn {
        border-radius: 6px;
        margin-bottom: 2px;
        pointer-events: auto;
    }

    .text-sm {
        font-size: 0.75em;
    }

    /* Dark mode overrides */
    @media (prefers-color-scheme: dark) {
        .alert-console-panel {
            background-color: #1e2126;
            color: #dee2e6;
        }
        .alert-console-panel .btn-close {
            filter: invert(1) grayscale(100%) brightness(200%);
        }
        .alert-console-panel .border-bottom {
            border-color: #495057 !important;
        }
    }
</style>
