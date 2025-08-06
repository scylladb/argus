<script lang="ts">
    import { run } from 'svelte/legacy';

    import dayjs from "dayjs";
    import { createEventDispatcher } from "svelte";

    interface Props {
        before: number | null;
        after: number | null;
    }

    let { before = $bindable(), after = $bindable() }: Props = $props();
    let isRange = $state(!!before);
    const dispatch = createEventDispatcher();

    let dateBefore = $derived(before ? dayjs.unix(before).format("YYYY-MM-DDTHH:mm") : null);
    let dateAfter = $derived(after ? dayjs.unix(after).format("YYYY-MM-DDTHH:mm") : null);
    run(() => {
        isRange ? null : before = null;
        dispatch("setDirty");
    });

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
        <input class="form-control" type="datetime-local" bind:value={dateAfter} oninput={handleAfterChange}>
        {#if isRange}
        <span class="input-group-text">Before</span>
            <input class="form-control" type="datetime-local" bind:value={dateBefore} oninput={handleBeforeChange}>
        {/if}
    </div>
</div>
