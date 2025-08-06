<script lang="ts">
    import { createScreenshotUrl } from "../Common/RunUtils";
    import ScreenshotModal from "./Components/ScreenshotModal.svelte";
    let { screenshots = [], testInfo, runId } = $props();

    let selectedScreenshot = $state(undefined);

</script>

<div class="d-flex p-2 align-items-center justify-content-center screenshots-holder">
{#each screenshots as screenshot_url}
        <div
            class="screenshot-thumb mx-1 mb-2"
            role="button"
            tabindex="0"
            style="background-image: url('{createScreenshotUrl(testInfo.test.plugin_name, runId, screenshot_url)}')"
            onclick={() => {
                selectedScreenshot = createScreenshotUrl(testInfo.test.plugin_name, runId, screenshot_url);
            }}
            onkeypress={() => {
                selectedScreenshot = createScreenshotUrl(testInfo.test.plugin_name, runId, screenshot_url);
            }}
></div>
{:else}
    <div class="text-muted text-center py-2">No screenshots submitted!</div>
{/each}
</div>
<ScreenshotModal bind:selectedScreenshot />

<style>
    .screenshot-thumb {
        border: solid 2px rgb(122, 122, 122);
        border-radius: 4px;
        width: 384px;
        height: 384px;
        background-size: cover;
        background-repeat: no-repeat;
    }

    .screenshot-thumb:hover {
        border: solid 2px rgb(209, 209, 209);
    }



    .screenshots-holder {
        flex-wrap: wrap;
    }
</style>
