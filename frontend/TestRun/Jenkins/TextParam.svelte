<script lang="ts">
    let { params = $bindable(), definition = {}, wrapper } = $props();
</script>

<textarea class="form-control" bind:value={params[definition.internalName]} onchange={(e) => wrapper ? wrapper(e, definition, params) : definition.onChange(e, params)} rows="4"></textarea>
