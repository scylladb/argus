<script>
    import { AVAILABLE_PLUGINS } from "../Common/PluginDispatch";
    export let runId;
    export let testInfo;
    export let buildNumber;


</script>

<svelte:component this={AVAILABLE_PLUGINS?.[testInfo.test.plugin_name] ?? AVAILABLE_PLUGINS.unknown} {runId} {testInfo} {buildNumber} on:closeRun on:investigationStatusChange on:runStatusChange on:cloneComplete />
