<script>
    export let params = {};
    export let definition = {};
</script>

<div>
    <select class="form-select" on:change={(e) => definition.onChange(e, params)} value={definition.args.value ?? definition.values[0]}>
        {#each definition.values as val, idx}
            <option value="{val}">{(definition.labels ?? definition.values)[idx]}</option>
        {/each}
    </select>
</div>