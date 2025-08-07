<script lang="ts">
    interface Props {
        children?: import('svelte').Snippet;
    }

    let { children }: Props = $props();
</script>

<div class="p-2 shadow mb-2 rounded bg-main">
    <div class="my-2 d-flex flex-wrap bg-lighter rounded shadow-sm">
        {#if children}{@render children()}{:else}<!-- optional fallback -->{/if}
    </div>
</div>
