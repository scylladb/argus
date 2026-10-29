<script lang="ts">
    import type { Snippet } from "svelte";

    interface Props {
        children: Snippet;
        class?: string;
    }

    let { children, class: extra = "" }: Props = $props();
</script>

<div class="inset rounded bg-light-one p-1 p-md-2 {extra}">
    {@render children()}
</div>

<style>
    .inset :global(.table) {
        --bs-table-border-color: #eaeaea;
    }

    :global([data-bs-theme="dark"]) .inset :global(.table) {
        --bs-table-border-color: #2b3035;
    }
</style>
