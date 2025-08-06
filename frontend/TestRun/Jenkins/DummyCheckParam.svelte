<script lang="ts">
    let { params, definition = {}, wrapper } = $props();

    if (definition.init) definition.init(params);

</script>

<div class="form-check form-switch">
    <input type="checkbox" class="form-check-input" onchange={(e) => wrapper ? wrapper(e, definition, params) : definition.onChange(e, params)} checked={definition.value}>
    <label type="checkbox" class="form-check-label">{definition.checkLabel}</label>
</div>
