<script lang="ts">
    import { createScreenshotUrl } from "../Common/RunUtils";
    import ScreenshotModal from "./Components/ScreenshotModal.svelte";

    interface Props {
        screenshots?: string[];
        testInfo: { test: { plugin_name: string } };
        runId: string;
    }

    let { screenshots = [], testInfo, runId }: Props = $props();

    let selectedScreenshot = $state("");

    const urls = $derived(screenshots.map((link) => createScreenshotUrl(testInfo.test.plugin_name, runId, link)));
</script>

{#if urls.length > 0}
    <div class="row row-cols-2 row-cols-md-3 row-cols-lg-4 row-cols-xxl-5 g-2 p-2">
        {#each urls as url, index}
            <div class="col">
                <button
                    type="button"
                    class="btn p-0 border rounded overflow-hidden ratio ratio-1x1"
                    onclick={() => (selectedScreenshot = url)}
                >
                    <img class="object-fit-cover w-100 h-100" src={url} alt="Screenshot {index + 1}" loading="lazy" decoding="async" />
                </button>
            </div>
        {/each}
    </div>
{:else}
    <div class="text-muted text-center py-2">No screenshots submitted!</div>
{/if}
<ScreenshotModal bind:selectedScreenshot screenshots={urls} />
