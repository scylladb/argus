<script lang="ts">
    import { alertStore } from "../Stores/AlertStore.js";
    import { onDestroy } from "svelte";
    import AlertMessage from "./AlertMessage.svelte";
    import { v4 as uuidv4 } from "uuid";
    let { flashes = [] } = $props();

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

{#if showOldMessages}
    <div class="alert-bucket-modal">
        <div class="d-flex align-items-center justify-content-center p-4">
            <div class="rounded bg-white p-4 h-50 w-75">
                <div class="mb-2 d-flex border-bottom pb-2">
                    <h5>Error console</h5>
                    <div class="ms-auto">
                        <button
                            class="btn btn-close"
                            onclick={() => {
                                showOldMessages = false;
                            }}
                        ></button>
                    </div>
                </div>
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
                <div>
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
    #alertWidget {
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
</style>
