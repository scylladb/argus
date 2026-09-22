<script>
    import { faQuestionCircle, faPlus, faTrash } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";


    /**
     * @typedef {Object} Props
     * @property {any} settingName
     * @property {any} definition
     * @property {any} settings
     */

    /** @type {Props} */
    let { settingName, definition, settings = $bindable() } = $props();

    let values = $state([...(settings[settingName] ?? definition.default ?? [])]);

    settings[settingName] = values;

    function addNewString() {
        values.push("");
    }

    function removeString(index) {
        values.splice(index, 1);
    }
</script>

<div>
    <div>{definition.displayName} <span title="{definition.help}"><Fa icon={faQuestionCircle}/></span></div>

    {#each values as value, index}
        <div class="input-group mb-2">
            <input type="text" class="form-control" bind:value={values[index]}>
            <button class="btn btn-outline-danger" title="Remove this entry" onclick={() => removeString(index)}>
                <Fa icon={faTrash}/>
            </button>
        </div>
    {/each}

    <button class="btn btn-outline-primary btn-sm" onclick={addNewString}>
        <Fa icon={faPlus}/> Add Filter
    </button>
</div>
