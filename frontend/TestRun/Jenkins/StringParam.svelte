<script lang="ts">
    let { params = $bindable(), definition = {}, wrapper } = $props();
</script>

<input class="form-control" type="text" bind:value={params[definition.internalName]} onchange={(e) => wrapper ? wrapper(e, definition, params) : definition.onChange(e, params)}>
