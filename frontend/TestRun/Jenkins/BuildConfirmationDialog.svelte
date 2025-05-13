<script>
    import { createEventDispatcher } from "svelte";

    /**
     * @type {Object} args
     */
    export let args;
    const dispatch = createEventDispatcher();
</script>

<div>
    This test contains no runs and no runs were found inside Jenkins. A build will be started without parameters to later retrieve them. Do you wish to continue?
    <div class="p-2">
        <button class="btn btn-primary me-1" on:click={() => dispatch("exit", { confirm: true })}>OK</button>
        <button class="btn btn-secondary" on:click={() => dispatch("exit", { confirm: false })}>Cancel</button>
    </div>
</div>
