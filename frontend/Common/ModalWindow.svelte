<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import { onMount, onDestroy } from "svelte";

    const dispatch = createEventDispatcher();

    interface Props {
        widthClass?: string;
        title?: import('svelte').Snippet;
        body?: import('svelte').Snippet;
    }

    let { widthClass = "w-50", title, body }: Props = $props();
    let innerWidth = $state(0);

    function handleKeyDown(event) {
        if (event.key === "Escape") {
            dispatch("modalClose");
        }
    }
</script>

<svelte:window onkeydown={handleKeyDown} bind:innerWidth={innerWidth} />
<div class="modal-window">
    <div class="d-flex align-items-center justify-content-center p-4">
        <div class="rounded bg-white p-4 {innerWidth >= 768 ? widthClass : "w-100"}">
            <div class="mb-2 d-flex border-bottom pb-2">
                <h5>
                    {#if title}{@render title()}{:else}<!-- optional fallback -->{/if}
                </h5>
                <div class="ms-auto">
                    <button
                        class="btn btn-close"
                        onclick={() => {
                            dispatch("modalClose");
                        }}
                    ></button>
                </div>
            </div>
            <div>
                {#if body}{@render body()}{:else}<!-- optional fallback -->{/if}
            </div>
        </div>
    </div>
</div>

<style>
    .w-50 {
        width: 50%;
    }

    .w-75 {
        width: 75%;
    }
    .modal-window {
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
