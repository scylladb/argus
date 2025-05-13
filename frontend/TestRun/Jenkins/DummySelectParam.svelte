<script>
    export let params = {};
    export let definition = {};
    export let wrapper;
</script>

<div>
    <select class="form-select" on:change={(e) => wrapper ? wrapper(e, definition, params) : definition.onChange(e, params)} value={definition.args.value ?? definition.values[0]}>
        {#each definition.values as val, idx}
            <option value="{val}">{(definition.labels ?? definition.values)[idx]}</option>
        {/each}
    </select>
</div>
