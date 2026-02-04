<script module>

    export interface SctConfiguration {
        run_id: string,
        name: string,
        content: string,
    }

</script>

<script lang="ts">
    import { onMount } from "svelte";
    import { sendMessage } from "../../Stores/AlertStore";
    import type { SCTTestRun } from "../TestRun.svelte";
    import RuntimeConfig from "../RuntimeConfig.svelte";
    import MiscConfig from "../MiscConfig.svelte";


    let {
        testRun
    }: {
        testRun: SCTTestRun
    } = $props();

    let configs: SctConfiguration[] = $state([]);
    let init = $state(false);

    const tryParseConfig = function (config: string) {
        try {
            JSON.parse(config);
            return true;
        } catch (e) {
            return false;
        }
    }

    const fetchConfigs = async function () {

        try {
            const res = await fetch(`/api/v1/client/${testRun.id}/config/all`);
            const json = await res.json();
            if (json.status !== "ok") {
                throw new Error(json.response.arguments[0]);
            }

            configs = json.response;
        } catch (e) {
            if (e instanceof Error) {
                sendMessage("error", e.message, "SctConfig::fetchConfigs");
            } else {
                sendMessage("error", "Backend error during config fetch.");
                console.trace();
            }
        } finally {
            init = true;
        }
    }

    onMount(async () => {
        await fetchConfigs();
    })

</script>

<div class="mb-2">
    <div class="p-2">
        <h4>Configuration files</h4>
        <p class="text-muted" style="font-size: 0.8rem">
            Configuration files used in this run.
        </p>
        {#each configs as config}
            {@const Component = tryParseConfig(config.content) ? RuntimeConfig : MiscConfig}
            <Component name={config.name} content={config.content}/>
        {:else}
            <div class="text-center text-muted p-2">
                {#if init}
                    No configs were submitted to this run.
                {:else}
                    <span class="spinner-border spinner-border-sm"></span> Fetching configs...
                {/if}
            </div>
        {/each}
    </div>
</div>

<style>

</style>
