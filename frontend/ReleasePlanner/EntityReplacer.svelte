<script>
    import { faArrowRight } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import ModalWindow from "../Common/ModalWindow.svelte";
    import ReleasePlannerGridView from "./ReleasePlannerGridView.svelte";
    import { createEventDispatcher } from "svelte";
    import SearchBar from "./SearchBar.svelte";

    export let entityType = "test";
    export let entity;
    export let targetRelease;

    let gridView = false;
    let replacement;
    const dispatch = createEventDispatcher();


    const handleGridPick = async function(e) {
        let [item] = e.detail.items;
        replacement = item;
        gridView = false;
        dispatch("entityReplaced", {
            original: entity,
            replacement: replacement,
        });
    };
</script>


{#if gridView}
    <ModalWindow on:modalClose={() => gridView = false}>
        <div slot="title">
            Replacing {entity.pretty_name || entity.display_name || entity.name}
        </div>
        <div slot="body">
            <div>
                <SearchBar release={targetRelease} mode="single" targetType={entityType} on:selected={handleGridPick} />
            </div>
            <ReleasePlannerGridView release={targetRelease} mode={"single"} groupOnly={entityType == "group"} on:gridViewConfirmed={handleGridPick}/>
        </div>
    </ModalWindow>
{/if}

<div class="d-flex align-items-center rounded shadow-sm">
    <div class="ms-2 p-2">
        {entity.pretty_name || entity.display_name || entity.name}
        {#if entity.release}
            <div class="text-muted text-sm">{entity.release}</div>
        {/if}
        {#if entity.group}
            <div class="text-muted text-sm">{entity.group}</div>
        {/if}
    </div>
    <div class="ms-auto p-2 border-start" class:border-end={!!replacement}>
        <button class="btn btn-success" on:click={() => gridView = true}>Replace <Fa icon={faArrowRight} /></button>
    </div>
    {#if replacement}
        <div class="ms-auto p-2">
            {replacement.pretty_name || replacement.display_name || replacement.name}
            {#if replacement.release}
                <div class="text-muted text-sm">{replacement.release}</div>
            {/if}
            {#if replacement.group}
                <div class="text-muted text-sm">{replacement.group}</div>
            {/if}
        </div>
    {/if}
</div>
