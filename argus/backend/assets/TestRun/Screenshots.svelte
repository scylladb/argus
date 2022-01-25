<script>
    import Fa from "svelte-fa";
    import { faTimes, faFileDownload } from "@fortawesome/free-solid-svg-icons";
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

{#if selectedScreenshot}
    <div class="screenshot-modal">
        <div class="text-end">
            <div class="d-inline-block screenshot-button">
                <a href={selectedScreenshot} target="_blank"
                    ><Fa color="#a0a0a0" icon={faFileDownload} /></a
                >
            </div>
            <div
                class="d-inline-block screenshot-button"
                on:click={() => {
                    selectedScreenshot = undefined;
                }}
            >
                <Fa icon={faTimes} />
            </div>
        </div>
        <div class="d-flex align-items-center justify-content-center my-2">
            <img
                class="screenshot-modal-image"
                src={selectedScreenshot}
                alt=""
            />
        </div>
    </div>
{/if}

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

    .screenshot-modal {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        overflow-y: scroll;
        background-color: rgba(0, 0, 0, 0.55);
        z-index: 9999;
    }

    .screenshot-button {
        font-size: 32pt;
        padding: 0 0.25rem;
        color: rgb(138, 138, 138);
        cursor: pointer;
    }

    .screenshot-button:hover {
        color: white;
    }

    .screenshot-button:last-child {
        padding-right: 1rem;
    }

    .screenshots-holder {
        flex-wrap: wrap;
    }
</style>
