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

    // Initialize settings if not already set
    if (!settings[settingName]) {
        settings[settingName] = definition.default || [];
    }

    function addNewString() {
        settings[settingName] = [...settings[settingName], ""];
    }

    function removeString(index) {
        settings[settingName] = settings[settingName].filter((_, i) => i !== index);
    }
</script>

<div>
    <div>{definition.displayName} <span title="{definition.help}"><Fa icon={faQuestionCircle}/></span></div>

    {#each settings[settingName] as value, index}
        <div class="input-group mb-2">
            <input type="text" class="form-control" bind:value={settings[settingName][index]}>
            <button class="btn btn-outline-danger" onclick={() => removeString(index)}>
                <Fa icon={faTrash}/>
            </button>
        </div>
    {/each}

    <button class="btn btn-outline-primary btn-sm" onclick={addNewString}>
        <Fa icon={faPlus}/> Add Filter
    </button>
</div>
