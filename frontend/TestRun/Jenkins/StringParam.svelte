<script>
    export let params;
    export let definition = {};
</script>

<input class="form-control" type="text" bind:value={params[definition.internalName]} on:change={(e) => definition.onChange(e, params)}>