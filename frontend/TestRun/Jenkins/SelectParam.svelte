<script lang="ts">
    let { params = $bindable({}), definition = {}, wrapper } = $props();
</script>

<div>
    {#if params[definition.internalName] && !definition.values.includes(params[definition.internalName])}
    <input class="form-control" type="text" disabled value="{params[definition.internalName]}">
    {:else}
        <select class="form-select" bind:value={params[definition.internalName]} onchange={(e) => wrapper ? wrapper(e, definition, params) : definition.onChange(e, params)}>

            {#each definition.values as val, idx}
                <option value="{val}">{(definition.labels ?? definition.values)[idx]}</option>
            {/each}
        </select>
    {/if}
</div>
