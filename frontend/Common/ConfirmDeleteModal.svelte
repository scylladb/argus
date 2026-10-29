<script lang="ts">
    import type { Snippet } from "svelte";
    import ModalWindow from "./ModalWindow.svelte";

    interface Props {
        heading: string;
        confirmName?: string | null;
        confirmLabel?: string;
        working?: boolean;
        onConfirm: () => void;
        onCancel: () => void;
        children?: Snippet;
    }

    let {
        heading,
        confirmName = null,
        confirmLabel = "Delete",
        working = false,
        onConfirm,
        onCancel,
        children,
    }: Props = $props();

    const inputId = $props.id();
    let typed = $state("");
    const ready = $derived(!working && (confirmName === null || typed === confirmName));
</script>

<ModalWindow on:modalClose={onCancel}>
    {#snippet title()}
        <div>{heading}</div>
    {/snippet}
    {#snippet body()}
        <div>
            {@render children?.()}
            {#if confirmName !== null}
                <div class="form-group mt-2">
                    <label for={inputId} class="form-label">
                        Type <span class="fw-bold">{confirmName}</span> to confirm
                    </label>
                    <input id={inputId} type="text" class="form-control" autocomplete="off" bind:value={typed} />
                </div>
            {/if}
            <div class="d-flex align-items-center my-2">
                <button type="button" disabled={!ready} class="btn btn-danger w-75 me-2" onclick={onConfirm}>
                    {confirmLabel}
                </button>
                <button type="button" disabled={working} class="btn btn-secondary w-25" onclick={onCancel}>
                    Cancel
                </button>
            </div>
        </div>
    {/snippet}
</ModalWindow>
