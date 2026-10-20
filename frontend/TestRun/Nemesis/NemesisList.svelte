<script lang="ts">
    import { tick } from "svelte";
    import { SvelteSet } from "svelte/reactivity";
    import Fa from "svelte-fa";
    import MultiSelect, { type ObjectOption } from "svelte-multiselect";
    import { faFilter, faServer, faSortDown, faSortUp } from "@fortawesome/free-solid-svg-icons";
    import NemesisRow from "./NemesisRow.svelte";
    import {
        DEFAULT_SORT,
        filterNemeses,
        isFiltering,
        nemesisKey,
        nemesisStatuses,
        nextSort,
        sortNemeses,
        statusClasses,
        statusLabel,
        type SortKey,
        type SortState,
    } from "./nemesisListing";
    import type { NemesisInfo, NemesisResource } from "./types";

    interface Props {
        nemeses?: NemesisInfo[];
        resources?: NemesisResource[];
        onSelectNode?: (name: string) => void;
    }

    interface StatusOption extends ObjectOption {
        label: string;
        value: string;
    }

    let { nemeses = [], resources = [], onSelectNode }: Props = $props();

    const COLUMNS: { key: SortKey; label: string; classes: string }[] = [
        { key: "name", label: "Nemesis", classes: "col" },
        { key: "node", label: "Target node", classes: "col-lg-3" },
        { key: "status", label: "Status", classes: "col-auto status-col" },
        { key: "start_time", label: "Started", classes: "col-auto time-col" },
        { key: "end_time", label: "Ended", classes: "col-auto time-col" },
    ];

    const PAGE_SIZES = [25, 50, 100, 250, 500];

    const uid = $props.id();
    let sort: SortState = $state(DEFAULT_SORT);
    let pageSize = $state(100);
    let extraPages = $state(0);
    let filters = $state({ text: "", node: null as string | null, excludedStatuses: new SvelteSet<string>() });
    let hoveredNode: string | null = $state(null);
    const expanded = new SvelteSet<string>();

    const visible = $derived(sortNemeses(filterNemeses(nemeses, filters), sort));
    const shown = $derived(visible.slice(0, pageSize * (extraPages + 1)));
    const remaining = $derived(visible.length - shown.length);
    const resourcesByName = $derived(new Map(resources.map((resource) => [resource.name, resource])));
    const statuses = $derived(nemesisStatuses(nemeses));
    const statusOptions: StatusOption[] = $derived(statuses.map((status) => ({ label: statusLabel(status), value: status })));
    const selectedStatuses = $derived(statusOptions.filter((option) => !filters.excludedStatuses.has(option.value)));
    const soleStatus = $derived(
        statuses.length > 1 && selectedStatuses.length === 1 ? selectedStatuses[0].value : null
    );
    const filtering = $derived(isFiltering(filters));

    $effect(() => {
        void [filters.text, filters.node, filters.excludedStatuses.size, sort.key, sort.direction, pageSize];
        extraPages = 0;
    });

    const toggleNodeFilter = (name: string) => {
        filters.node = filters.node === name ? null : name;
    };

    const toggleStatusFilter = (status: string) => {
        const wasSole = soleStatus === status;
        filters.excludedStatuses.clear();
        if (!wasSole) {
            for (const other of statuses.filter((candidate) => candidate !== status)) {
                filters.excludedStatuses.add(other);
            }
        }
    };

    const resetStatuses = async () => {
        await tick();
        filters.excludedStatuses.clear();
    };

    const excludeStatuses = (options: StatusOption[]) => {
        for (const option of options) {
            filters.excludedStatuses.add(option.value);
        }
        if (filters.excludedStatuses.size === statuses.length) {
            resetStatuses();
        }
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
        <div class="status-select d-flex align-items-stretch">
            <label class="input-group-text small py-0" for="{uid}-status">Status</label>
            <MultiSelect
                id="{uid}-status"
                options={statusOptions}
                selected={selectedStatuses}
                key={(option) => option.value}
                placeholder="Every status"
                removeAllTitle="Reset to every status"
                onadd={({ option }) => filters.excludedStatuses.delete(option.value)}
                onremove={({ option }) => excludeStatuses([option])}
                onremoveAll={({ options }) => excludeStatuses(options)}
                onselectAll={() => filters.excludedStatuses.clear()}
            >
                {#snippet children({ option })}
                    <span class="badge rounded-pill {statusClasses(option.value)}">{option.label}</span>
                {/snippet}
            </MultiSelect>
        </div>
        <div class="input-group input-group-sm page-size">
            <label class="input-group-text" for="{uid}-page-size">Show</label>
            <select id="{uid}-page-size" class="form-select" bind:value={pageSize}>
                {#each PAGE_SIZES as size (size)}
                    <option value={size}>{size}</option>
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
        <div class="nemesis-rows border rounded bg-white" role="rowgroup">
            {#each shown as nemesis (nemesisKey(nemesis))}
                <NemesisRow
                    {nemesis}
                    resource={resourcesByName.get(nemesis.target_node.name)}
                    open={expanded.has(nemesisKey(nemesis))}
                    highlighted={hoveredNode !== null && nemesis.target_node.name === hoveredNode}
                    filtered={filters.node === nemesis.target_node.name}
                    statusOnly={soleStatus === nemesis.status}
                    onToggle={() => toggle(nemesisKey(nemesis))}
                    {onSelectNode}
                    onHoverNode={(name) => (hoveredNode = name)}
                    onFilterNode={toggleNodeFilter}
                    onFilterStatus={toggleStatusFilter}
                />
            {:else}
                <p class="text-muted text-center m-0 p-3">No nemesis matches the filter.</p>
            {/each}
            {#if remaining > 0}
                <div class="d-flex flex-wrap align-items-center justify-content-center gap-3 p-2 small text-muted border-top">
                    <span>Showing {shown.length} of {visible.length}</span>
                    <button type="button" class="btn btn-sm btn-outline-primary" onclick={() => (extraPages += 1)}>
                        Load {Math.min(pageSize, remaining)} more
                    </button>
                </div>
            {/if}
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

    .status-select {
        --sms-bg: var(--bs-body-bg);
        --sms-options-bg: var(--bs-body-bg);
        --sms-text-color: var(--bs-body-color);
        --sms-placeholder-color: var(--bs-secondary-color);
        --sms-placeholder-opacity: 1;
        --sms-border: var(--bs-border-width) solid var(--bs-border-color);
        --sms-focus-border: var(--bs-border-width) solid var(--bs-primary);
        --sms-border-radius: 0 var(--bs-border-radius-sm) var(--bs-border-radius-sm) 0;
        --sms-active-color: var(--bs-primary-bg-subtle);
        --sms-selected-bg: transparent;
        --sms-selected-li-padding: 0;
        --sms-min-height: calc(1.5em + 0.5rem + 2px);
        --sms-padding: 0 0.25rem;
        --sms-font-size: 0.875rem;
        --sms-options-z-index: 1060;
        font-size: 0.875rem;
    }

    .status-select label {
        border-right: 0;
        border-radius: var(--bs-border-radius-sm) 0 0 var(--bs-border-radius-sm);
    }

    .status-select :global(div.multiselect > ul.selected) {
        align-items: center;
        gap: 0.125rem;
        margin: 0;
    }

    .status-select :global(div.multiselect > ul.selected > li) {
        margin: 0;
    }

    .status-select :global(div.multiselect > ul.options > li) {
        padding: 0.25rem 0.5rem;
    }

    @media (min-width: 992px) {
        .filter-group {
            max-width: 28rem;
        }

        .status-select {
            max-width: 32rem;
        }

        .page-size {
            max-width: 9rem;
        }

        .nemesis-list :global(.status-col) {
            width: 7rem;
        }

        .nemesis-list :global(.time-col) {
            width: 10.5rem;
        }
    }
</style>
