<script>
    import { AVAILABLE_PLUGINS } from "../Common/PluginDispatch";
    export let runId;
    export let testInfo;
    export let buildNumber;
    export let tab;


</script>

<svelte:component this={AVAILABLE_PLUGINS?.[testInfo.test.plugin_name] ?? AVAILABLE_PLUGINS.unknown} {runId} {testInfo} {buildNumber} {tab} on:closeRun on:investigationStatusChange on:runStatusChange on:cloneComplete />
