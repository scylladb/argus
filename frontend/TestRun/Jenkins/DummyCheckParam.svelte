<script lang="ts">
    let { params, definition = {}, wrapper } = $props();

    if (definition.init) definition.init(params);

</script>

<div class="form-check form-switch">
    <label class="form-check-label"><input type="checkbox" class="form-check-input" onchange={(e) => wrapper ? wrapper(e, definition, params) : definition.onChange(e, params)} checked={definition.value}> {definition.checkLabel}</label>
</div>
