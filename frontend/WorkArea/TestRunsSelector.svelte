<script>
    import { createEventDispatcher, onMount } from "svelte";
    import { extractBuildNumber } from "../Common/RunUtils";
    import { StatusButtonCSSClassMap } from "../Common/TestStatus";

    export let testInfo = {};
    export let runs = [];
    export let clickedTestRuns = {};

    const dispatch = createEventDispatcher();
    let sticky = false;
    let header;

    onMount(() => {
        let observer = new IntersectionObserver((entries) => {
            let entry = entries[0];
            if (!entry) return;
            if (entry.intersectionRatio == 0 && !entry.isIntersecting) {
                sticky = true;
            } else {
                sticky = false;
            }
        }, {
            threshold: [0, 0.25, 0.5, 0.75, 1]
        });
        observer.observe(header);
    });

</script>

<div class="h-small" bind:this={header}></div>
<div class="p-2 mb-2 bg-main" class:sticky={sticky} class:border={sticky} class:shadow={sticky}>
    {#if sticky}
        <div class="mb-1 p-1">
            {testInfo.test.name} ({testInfo.release.name}/{testInfo.group.name})
        </div>
    {/if}
    {#each runs as run (run.id)}
        <div class="me-2 d-inline-block">
            <button
                class:active={clickedTestRuns[run.id]}
                class="btn {StatusButtonCSSClassMap[run.status]}"
                type="button"
                on:click={() => dispatch("runClick", { runId: run.id })}
            >
                #{extractBuildNumber(run)}
            </button>
        </div>
    {/each}
</div>

<style>
    .active::before {
        font-family: "Noto Sans Packaged", "Noto Sans", sans-serif;
        content: "● ";
    }

    .sticky {
        position: sticky;
        top: 12px;
        z-index: 999;
        margin: 1em;
        border-radius: 4px;
    }

    .h-small {
        height: 4px;
    }
</style>
