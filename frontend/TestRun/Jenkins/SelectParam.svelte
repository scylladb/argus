<script>
    export let params = {};
    export let definition = {};
</script>

<div>
    {#if params[definition.internalName] && !definition.values.includes(params[definition.internalName])}
    <input class="form-control" type="text" disabled value="{params[definition.internalName]}">
    {:else}
        <select class="form-select" bind:value={params[definition.internalName]} on:change={(e) => definition.onChange(e, params)}>

            {#each definition.values as val, idx}
                <option value="{val}">{(definition.labels ?? definition.values)[idx]}</option>
            {/each}
        </select>
    {/if}
</div>