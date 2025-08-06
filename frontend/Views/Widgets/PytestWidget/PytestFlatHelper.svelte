<script lang="ts">
    import { createEventDispatcher, onMount } from "svelte";
    interface Props {
        children?: import('svelte').Snippet;
    }

    let { children }: Props = $props();

    const dispatch = createEventDispatcher();

    onMount(() => {
        dispatch("open");
    });
</script>
{#if children}{@render children()}{:else}

{/if}
