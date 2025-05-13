<script>
    export let params;
    export let definition = {};
    export let wrapper;

    if (definition.init) definition.init(params);

</script>

<div class="form-check form-switch">
    <input type="checkbox" class="form-check-input" on:change={(e) => wrapper ? wrapper(e, definition, params) : definition.onChange(e, params)} checked={definition.value}>
    <label type="checkbox" class="form-check-label">{definition.checkLabel}</label>
</div>
