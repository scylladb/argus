<script lang="ts">
    import { createEventDispatcher, type Snippet } from "svelte";
    import { addModal, removeModal } from "../Stores/ModalStore";

    const dispatch = createEventDispatcher();

    interface Props {
        widthClass?: string;
        title?: Snippet;
        body?: Snippet;
    }

    let { widthClass = "w-50", title, body }: Props = $props();
    let innerWidth = $state(0);
    let dialog: HTMLDialogElement | undefined = $state();
    let frame: HTMLElement | undefined = $state();
    const titleId = $props.id();
    let pressedOutside = false;
    let releasedOutside = false;

    const outside = (target: EventTarget | null) => target === dialog || target === frame;

    const closeOnOutsideClick = (event: MouseEvent) => {
        const close = pressedOutside && releasedOutside && outside(event.target);
        pressedOutside = false;
        releasedOutside = false;
        if (close) dialog?.close();
    };

    $effect(() => {
        if (!dialog) return;
        const active = document.activeElement;
        const opener = active instanceof HTMLElement && active !== document.body ? active : null;
        const shown = dialog;
        shown.showModal();
        addModal(shown);
        return () => {
            removeModal(shown);
            const focused = document.activeElement;
            if (opener?.isConnected && (focused === null || focused === document.body)) {
                opener.focus();
            }
        };
    });
</script>

<svelte:window bind:innerWidth={innerWidth} />
<dialog
    bind:this={dialog}
    class="modal-window"
    aria-labelledby={title ? titleId : undefined}
    onpointerdown={(event) => (pressedOutside = outside(event.target))}
    onpointerup={(event) => (releasedOutside = outside(event.target))}
    onclick={closeOnOutsideClick}
    onclose={() => dispatch("modalClose")}
>
    <div class="d-flex align-items-center justify-content-center p-4" bind:this={frame}>
        <div class="rounded bg-white p-4 {innerWidth >= 768 ? widthClass : "w-100"}">
            <div class="mb-2 d-flex border-bottom pb-2">
                <h5 id={titleId}>
                    {@render title?.()}
                </h5>
                <div class="ms-auto">
                    <button
                        class="btn btn-close"
                        aria-label="Close"
                        title="Close"
                        onclick={() => {
                            dispatch("modalClose");
                        }}
                    ></button>
                </div>
            </div>
            <div>
                {@render body?.()}
            </div>
        </div>
    </div>
</dialog>

<style>
    .w-50 {
        width: 50%;
    }

    .w-75 {
        width: 75%;
    }

    dialog.modal-window {
        position: fixed;
        inset: 0;
        width: 100%;
        height: 100%;
        max-width: none;
        max-height: none;
        margin: 0;
        padding: 0;
        border: 0;
        background: transparent;
        overflow-y: auto;
        overscroll-behavior: contain;
    }

    dialog.modal-window::backdrop {
        background-color: rgba(0, 0, 0, 0.55);
        overflow: hidden;
        overscroll-behavior: contain;
    }
</style>
