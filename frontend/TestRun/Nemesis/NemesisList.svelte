<script lang="ts">
    import { SvelteSet } from "svelte/reactivity";
    import Fa from "svelte-fa";
    import { faFilter, faServer, faSortDown, faSortUp } from "@fortawesome/free-solid-svg-icons";
    import NemesisRow from "./NemesisRow.svelte";
    import {
        DEFAULT_SORT,
        EMPTY_FILTERS,
        filterNemeses,
        isFiltering,
        nemesisKey,
        nemesisStatuses,
        nextSort,
        sortNemeses,
        statusLabel,
        type NemesisFilters,
        type SortKey,
        type SortState,
    } from "./nemesisListing";
    import type { NemesisInfo, NemesisResource } from "./types";

    interface Props {
        nemeses?: NemesisInfo[];
        resources?: NemesisResource[];
        onSelectNode?: (name: string) => void;
    }

    let { nemeses = [], resources = [], onSelectNode }: Props = $props();

    const COLUMNS: { key: SortKey; label: string; classes: string }[] = [
        { key: "name", label: "Nemesis", classes: "col" },
        { key: "node", label: "Target node", classes: "col-lg-3" },
        { key: "status", label: "Status", classes: "col-auto status-col" },
        { key: "start_time", label: "Started", classes: "col-auto time-col" },
        { key: "end_time", label: "Ended", classes: "col-auto time-col" },
    ];

    const uid = $props.id();
    let sort: SortState = $state(DEFAULT_SORT);
    let filters: NemesisFilters = $state({ ...EMPTY_FILTERS });
    let hoveredNode: string | null = $state(null);
    const expanded = new SvelteSet<string>();

    const visible = $derived(sortNemeses(filterNemeses(nemeses, filters), sort));
    const resourcesByName = $derived(new Map(resources.map((resource) => [resource.name, resource])));
    const statuses = $derived(nemesisStatuses(nemeses));
    const filtering = $derived(isFiltering(filters));

    const toggleNodeFilter = (name: string) => {
        filters.node = filters.node === name ? null : name;
    };

    const toggle = (key: string) => {
        if (!expanded.delete(key)) {
            expanded.add(key);
        }
    };

    const ariaSort = (key: SortKey): "ascending" | "descending" | "none" => {
        if (sort.key !== key) {
            return "none";
        }
        return sort.direction === "asc" ? "ascending" : "descending";
    };
</script>

{#if nemeses.length === 0}
    <p class="text-muted text-center m-0 p-3">No nemeses were reported for this run.</p>
{:else}
    <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
        <div class="input-group input-group-sm filter-group">
            <label class="input-group-text" for="{uid}-filter"><Fa icon={faFilter} />&nbsp;Filter</label>
            <input
                id="{uid}-filter"
                class="form-control"
                type="search"
                placeholder="name, node, status, time, description"
                bind:value={filters.text}
            />
        </div>
        <div class="input-group input-group-sm status-group">
            <label class="input-group-text" for="{uid}-status">Status</label>
            <select id="{uid}-status" class="form-select" bind:value={filters.status}>
                <option value="">All statuses</option>
                {#each statuses as status (status)}
                    <option value={status}>{statusLabel(status)}</option>
                {/each}
            </select>
        </div>
        {#if filters.node}
            <span class="badge rounded-pill text-bg-primary d-inline-flex align-items-center gap-1 font-monospace">
                <Fa icon={faServer} />
                {filters.node}
                <button
                    type="button"
                    class="btn-close btn-close-white"
                    aria-label="Clear the node filter"
                    onclick={() => (filters.node = null)}
                ></button>
            </span>
        {/if}
        <span class="small text-muted ms-auto">
            {#if filtering}
                {visible.length} of {nemeses.length} match
            {:else if nemeses.length === 1}
                1 nemesis
            {:else}
                {nemeses.length} nemeses
            {/if}
        </span>
    </div>
    <div class="nemesis-list p-2 border rounded bg-light-three" role="table" aria-label="Nemeses">
        <div class="nemesis-header row g-2 px-2 pb-2 small text-muted text-uppercase d-none d-lg-flex" role="row">
            {#each COLUMNS as column (column.key)}
                <div class={column.classes} role="columnheader" aria-sort={ariaSort(column.key)}>
                    <button
                        type="button"
                        class="btn btn-link btn-sm p-0 text-decoration-none text-reset text-uppercase"
                        class:fw-semibold={sort.key === column.key}
                        onclick={() => (sort = nextSort(sort, column.key))}
                    >
                        {column.label}
                        {#if sort.key === column.key}
                            <Fa icon={sort.direction === "asc" ? faSortUp : faSortDown} />
                        {/if}
                    </button>
                </div>
            {/each}
        </div>
        <div class="nemesis-rows border rounded bg-white">
            {#each visible as nemesis (nemesisKey(nemesis))}
                <NemesisRow
                    {nemesis}
                    resource={resourcesByName.get(nemesis.target_node.name)}
                    open={expanded.has(nemesisKey(nemesis))}
                    highlighted={hoveredNode !== null && nemesis.target_node.name === hoveredNode}
                    filtered={filters.node === nemesis.target_node.name}
                    onToggle={() => toggle(nemesisKey(nemesis))}
                    {onSelectNode}
                    onHoverNode={(name) => (hoveredNode = name)}
                    onFilterNode={toggleNodeFilter}
                />
            {:else}
                <p class="text-muted text-center m-0 p-3">No nemesis matches the filter.</p>
            {/each}
        </div>
    </div>
{/if}

<style>
    .nemesis-list {
        box-shadow: var(--bs-box-shadow-inset);
    }

    .nemesis-header {
        overflow-y: hidden;
        scrollbar-gutter: stable;
    }

    .nemesis-rows {
        max-height: 70vh;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }

    .nemesis-rows :global(.nemesis-row + .nemesis-row) {
        border-top: 1px solid var(--bs-border-color);
    }

    @media (min-width: 992px) {
        .filter-group {
            max-width: 28rem;
        }

        .status-group {
            max-width: 14rem;
        }

        .nemesis-list :global(.status-col) {
            width: 7rem;
        }

        .nemesis-list :global(.time-col) {
            width: 10.5rem;
        }
    }
</style>
