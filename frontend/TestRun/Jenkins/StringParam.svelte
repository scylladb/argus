<script>
    export let params;
    export let definition = {};
    export let wrapper;
</script>

<input class="form-control" type="text" bind:value={params[definition.internalName]} on:change={(e) => wrapper ? wrapper(e, definition, params) : definition.onChange(e, params)}>
