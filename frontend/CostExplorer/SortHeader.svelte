<script lang="ts" generics="K extends string">
    import type { Sort, SortDirection } from "./sort.svelte";

    interface Props {
        sort: Sort<K>;
        key: K;
        label: string;
        align?: "start" | "end";
        defaultDirection?: SortDirection;
        class?: string;
    }

    let { sort, key, label, align = "start", defaultDirection, class: extra = "" }: Props = $props();

    const active = $derived(sort.key === key);
    const ariaSort = $derived(active ? (sort.direction === "asc" ? "ascending" : "descending") : "none");
    const fallback = $derived(defaultDirection ?? (align === "end" ? "desc" : "asc"));
</script>

<th scope="col" class="text-{align} {extra}" aria-sort={ariaSort}>
    <button type="button" class="sort-button" class:active onclick={() => sort.toggle(key, fallback)}>
        {label}<span class="arrow" aria-hidden="true">{active ? (sort.direction === "asc" ? "▲" : "▼") : ""}</span>
    </button>
</th>

<style>
    .sort-button {
        background: none;
        border: 0;
        padding: 0;
        font: inherit;
        color: inherit;
        cursor: pointer;
        white-space: nowrap;
    }

    .sort-button:hover,
    .sort-button.active {
        color: var(--bs-primary);
    }

    .arrow {
        display: inline-block;
        width: 1em;
        font-size: 0.7em;
        text-align: center;
    }
</style>
