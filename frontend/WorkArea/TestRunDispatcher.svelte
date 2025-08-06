<script lang="ts">
    import { AVAILABLE_PLUGINS } from "../Common/PluginDispatch";
    let {
        runId,
        testInfo,
        buildNumber,
        tab
    } = $props();



    const SvelteComponent = $derived(AVAILABLE_PLUGINS?.[testInfo.test.plugin_name] ?? AVAILABLE_PLUGINS.unknown);
</script>

<SvelteComponent {runId} {testInfo} {buildNumber} {tab} on:closeRun on:investigationStatusChange on:runStatusChange on:cloneComplete />
