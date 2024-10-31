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

<div class="form">
    <input type="number" class="form-control" bind:value={settings[settingName]}>
    <label type="text" class="form-label">{definition.displayName}</label> <span title="{definition.help}"><Fa icon={faQuestionCircle}/></span>
</div>
