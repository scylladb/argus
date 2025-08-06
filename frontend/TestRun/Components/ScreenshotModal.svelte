<script lang="ts">
    import {faFileDownload, faTimes} from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import {onMount, onDestroy} from "svelte";

    interface Props {
        selectedScreenshot: string;
    }

    let { selectedScreenshot = $bindable() }: Props = $props();
    function handleKeyDown(event: KeyboardEvent) {
        if (event.key === "Escape") {
            selectedScreenshot = "";
        }
    }
</script>

<svelte:window onkeydown={handleKeyDown} />
{#if selectedScreenshot}
    <div class="screenshot-modal">
        <div class="text-end">
            <div class="d-inline-block screenshot-button">
                <a href="{selectedScreenshot}?download=1" target="_blank">
                    <Fa color="#a0a0a0" icon={faFileDownload}/>
                </a>
            </div>
            <div
                    class="d-inline-block screenshot-button"
                    onclick={() => {
                selectedScreenshot = "";
            }}
            >
                <Fa icon={faTimes}/>
            </div>
        </div>
        <div class="d-flex align-items-center justify-content-center my-2">
            <img
                    class="screenshot-modal-image"
                    src={selectedScreenshot}
                    alt="Screenshot"
            />
        </div>
    </div>
{/if}


<style>
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

</style>
