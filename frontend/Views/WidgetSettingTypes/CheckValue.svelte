<script>
    import { faQuestionCircle } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";

    /**
     * @type {{
     *  default: boolean,
     *  help: string,
     *  displayName: string,
     *  type: Object
     * }}
     */
    export let settingName;
    export let definition;
    export let settings;
</script>

<div class="form-check form-switch">
    <input type="checkbox" class="form-check-input" bind:checked={settings[settingName]}>
    <label type="checkbox" class="form-check-label">{definition.displayName}</label> <span title="{definition.help}"><Fa icon={faQuestionCircle}/></span>
</div>
