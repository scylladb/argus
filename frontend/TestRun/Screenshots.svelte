<script>
    import ScreenshotModal from "./Components/ScreenshotModal.svelte";
    export let screenshots = [];

    let selectedScreenshot = undefined;
</script>

<div class="d-flex p-2 align-items-center justify-content-center screenshots-holder">
{#each screenshots as screenshot_url}
        <div
            class="screenshot-thumb mx-1 mb-2"
            role="button"
            style="background-image: url('{screenshot_url}')"
            on:click={() => {
                selectedScreenshot = screenshot_url;
            }}
        />
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
