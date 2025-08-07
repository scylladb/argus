<script>
    import { faQuestionCircle } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";


    /**
     * @typedef {Object} Props
     * @property {any} settingName
     * @property {any} definition
     * @property {any} settings
     */

    /** @type {Props} */
    let { settingName, definition, settings = $bindable() } = $props();
</script>

<div>
    <div>{definition.displayName} <span title="{definition.help}"><Fa icon={faQuestionCircle}/></span></div>
    <select class="form-select" multiple size=10 bind:value={settings[settingName]}>
        {#each definition.values as value, idx}
            <option value="{value}">{(definition.labels ?? definition.values)[idx]}</option>
        {/each}
    </select>
</div>
