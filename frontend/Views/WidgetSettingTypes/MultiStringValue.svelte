<script>
    import { faQuestionCircle, faPlus, faTrash } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";

    /**
     * @type {{
     *  default: string[],
     *  help: string,
     *  displayName: string,
     *  type: Object
     * }}
     */
    export let settingName;
    export let definition;
    export let settings;

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
            <button class="btn btn-outline-danger" on:click={() => removeString(index)}>
                <Fa icon={faTrash}/>
            </button>
        </div>
    {/each}

    <button class="btn btn-outline-primary btn-sm" on:click={addNewString}>
        <Fa icon={faPlus}/> Add Filter
    </button>
</div>
