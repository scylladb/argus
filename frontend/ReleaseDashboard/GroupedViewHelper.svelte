<script lang="ts">
    interface Props {
        children?: import('svelte').Snippet;
    }

    let { children }: Props = $props();
</script>

<div>
    {#if children}{@render children()}{:else}<!-- optional fallback -->{/if}
</div>
