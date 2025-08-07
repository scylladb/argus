<script lang="ts">
    let { params, definition = {} } = $props();
</script>

<div class="form-check form-switch">
    <input type="checkbox" class="form-check-input" onchange={(e) => definition.onChange(e, params)} checked={params[definition.internalName] === "true"}>
    <label class="form-check-label">{definition.checkLabel}</label>
</div>
