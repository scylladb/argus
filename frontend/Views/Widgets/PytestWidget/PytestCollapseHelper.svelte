<script lang="ts">
    import { Collapse } from "bootstrap";
    import { createEventDispatcher } from "svelte";
    interface Props {
        children?: import('svelte').Snippet;
    }

    let { children }: Props = $props();

    let collapse: Element = $state();
    let firstTime = true;
    const dispatch = createEventDispatcher();

    const handleAccordionOpen = function () {
        if (firstTime) {
            firstTime = false;
            dispatch("open");
        }

        new Collapse(collapse, { toggle: true });
    };
</script>

<div class="accordion">
    <div class="accordion-item">
        <h2 class="accordion-header" id="headingOne">
            <button class="accordion-button collapsed" type="button" onclick={handleAccordionOpen}> Pytest Overview </button>
        </h2>
        <div bind:this={collapse} class="accordion-collapse collapse">
            <div class="accordion-body">
                {@render children?.()}
            </div>
        </div>
    </div>
</div>
