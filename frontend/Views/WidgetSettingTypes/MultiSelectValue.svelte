<script>
    import { faQuestionCircle } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";

    /**
     * @type {{
     *  default: any[],
     *  help: string,
     *  displayName: string,
     *  type: Object,
     *  values: string[],
     *  labels: string[],
     * }}
     */
    export let settingName;
    export let definition;
    export let settings;
</script>

<div>
    <div>{definition.displayName} <span title="{definition.help}"><Fa icon={faQuestionCircle}/></span></div>
    <select class="form-select" multiple size=10 bind:value={settings[settingName]}>
        {#each definition.values as value, idx}
            <option value="{value}">{(definition.labels ?? definition.values)[idx]}</option>
        {/each}
    </select>
</div>
