<script>
    import { createEventDispatcher } from "svelte";

    const dispatch = createEventDispatcher();
</script>

<div class="modal-window">
    <div class="d-flex align-items-center justify-content-center p-4">
        <div class="rounded bg-white p-4 h-50">
            <div class="mb-2 d-flex border-bottom pb-2">
                <h5>
                    <slot name="title"><!-- optional fallback --></slot>
                </h5>
                <div class="ms-auto">
                    <button 
                        class="btn btn-close"
                        on:click={() => {
                            dispatch("modalClose");
                        }}
                    ></button>
                </div>
            </div>
            <div>
                <slot name="body"><!-- optional fallback --></slot>
            </div>
        </div>
    </div>
</div>

<style>
    .h-50 {
        width: 50%;
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