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

<div class="form">
    <input id="string-{settingName}" type="text" class="form-control" bind:value={settings[settingName]}>
    <label for="string-{settingName}" class="form-label">{definition.displayName}</label> <span title="{definition.help}"><Fa icon={faQuestionCircle}/></span>
</div>
