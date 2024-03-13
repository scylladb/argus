<script>
    import { createEventDispatcher } from "svelte";
    import { sanitizeSelector } from "../../Common/TextUtils";

    /**
     * @type {{params: {_class: string, name: string, value: string, description: string}[]}}
     */
    export let args;
    let showEmptyParams = false;
    let buildParams = args.params.reduce((acc, val) => {
        acc[val.name] = val.value;
        return acc;
    }, {});
    const dispatch = createEventDispatcher();

</script>

<div>
    <div class="mb-1">
        <div class="btn-group btn-group-sm" role="group">
            <button 
                type="button"
                class="btn"
                class:btn-primary={!showEmptyParams}
                class:btn-outline-primary={showEmptyParams}
                on:click={() => (showEmptyParams = false)}
            >This build parameters</button>
            <button 
                type="button"
                class="btn"
                class:btn-primary={showEmptyParams}
                class:btn-outline-primary={!showEmptyParams}
                on:click={() => (showEmptyParams = true)}
            >All parameters</button>
        </div>
    </div>
    <div class="mb-2">
        {#each args.params as param}
            {#if param.value || showEmptyParams}
                <div class="mb-1">
                    <label class="form-label fw-bold" for={param.name}>{param.name}</label>
                    <input class="form-control" id={param.name} type="text" bind:value={buildParams[param.name]}>
                    <div id="paramHelp{sanitizeSelector(param.name)}" class="form-text">{@html param.description}</div>
                </div>
            {/if}
        {/each}
    </div>
    <div class="text-end">
        <button
            class="btn btn-success w-100 mb-1"
            on:click={() => dispatch("exit", { buildParams: buildParams })}
        >Build</button>
    </div>
</div>