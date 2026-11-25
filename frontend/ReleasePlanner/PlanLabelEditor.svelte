<script lang="ts">
    import Fa from "svelte-fa";
    import { faPlus, faXmark } from "@fortawesome/free-solid-svg-icons";

    interface Props {
        labels: string[];
        listId: string;
        itemName: string;
        onadd: (label: string) => string | undefined;
        onremove: (label: string) => void;
    }

    let { labels, listId, itemName, onadd, onremove }: Props = $props();

    let draft = $state("");
    let error = $state("");

    const add = () => {
        const refused = onadd(draft);
        error = refused ?? "";
        if (!refused) draft = "";
    };

    const onkeydown = (event: KeyboardEvent) => {
        if (event.key === "Enter") {
            event.preventDefault();
            add();
        }
    };
</script>

<div class="d-flex flex-wrap align-items-center gap-1 mt-1">
    {#each labels as label (label)}
        <span class="badge rounded-pill text-bg-info d-inline-flex align-items-center gap-1">
            {label}
            <button type="button" class="btn btn-link p-0 lh-1 text-reset" aria-label="Remove label {label} from {itemName}"
                    title="Remove label" onclick={() => onremove(label)}>
                <Fa icon={faXmark} size="xs" />
            </button>
        </span>
    {/each}
    <div class="input-group input-group-sm label-input">
        <input class="form-control" type="text" list={listId} placeholder="Add label" bind:value={draft} {onkeydown}
               aria-label="New label for {itemName}" aria-invalid={error ? "true" : undefined}>
        <button type="button" class="btn btn-outline-secondary" aria-label="Add label to {itemName}" title="Add label"
                onclick={add}>
            <Fa icon={faPlus} />
        </button>
    </div>
    {#if error}
        <span class="small text-danger" role="alert">{error}</span>
    {/if}
</div>

<style>
    .label-input {
        width: 10rem;
    }
</style>
