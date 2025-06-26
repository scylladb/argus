<script lang="ts">
    import dayjs from "dayjs";
    import { createEventDispatcher } from "svelte";

    export let before: number | null;
    export let after: number | null;
    let isRange = !!before;
    const dispatch = createEventDispatcher();

    $: dateBefore = before ? dayjs.unix(before).format("YYYY-MM-DDTHH:mm") : null;
    $: dateAfter = after ? dayjs.unix(after).format("YYYY-MM-DDTHH:mm") : null;
    $: {
        isRange ? null : before = null;
        dispatch("setDirty");
    }

    const handleAfterChange = function(e: Event) {
        const input = e.currentTarget as HTMLInputElement;
        if (!input) {
            after = null;
            return;
        }
        after = dayjs(input.value, "YYYY-MM-DDTHH:mm").unix();
        dispatch("setDirty");
    };

    const handleBeforeChange = function(e: Event) {
        const input = e.currentTarget as HTMLInputElement;
        if (!input) {
            before = null;
            return;
        }
        before = dayjs(input.value, "YYYY-MM-DDTHH:mm").unix();
        dispatch("setDirty");
    };
</script>

<div class="mb-2">
    <div class="input-group">
        <span class="input-group-text">
            <input class="form-check-input mt-0 me-1" type="checkbox" bind:checked={isRange}>
            Range
        </span>
        <span class="input-group-text">After</span>
        <input class="form-control" type="datetime-local" bind:value={dateAfter} on:input={handleAfterChange}>
        {#if isRange}
        <span class="input-group-text">Before</span>
            <input class="form-control" type="datetime-local" bind:value={dateBefore} on:input={handleBeforeChange}>
        {/if}
    </div>
</div>
