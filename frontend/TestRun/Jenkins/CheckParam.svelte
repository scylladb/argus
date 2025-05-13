<script>
    export let params;
    export let definition = {};
</script>

<div class="form-check form-switch">
    <input type="checkbox" class="form-check-input" on:change={(e) => definition.onChange(e, params)} checked={params[definition.internalName] === "true"}>
    <label type="checkbox" class="form-check-label">{definition.checkLabel}</label>
</div>
