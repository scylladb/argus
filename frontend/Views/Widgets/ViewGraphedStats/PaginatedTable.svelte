<script lang="ts">
    import humanizeDuration from "humanize-duration";
    import { timestampToISODate } from "../../../Common/DateUtils.js";
    import type { NemesisData, TestRun } from "./Interfaces";

    interface Props {
        /** @description Array of items to display (either NemesisData or TestRun) */
        items: (NemesisData | TestRun)[];
        /** @description Number of items to show per page */
        itemsPerPage?: number;
        /** @description Table title */
        title: string;
        sortField: string;
        sortDirection: "asc" | "desc";
        /**
     * @description Table column definitions
     * @type {Array<{key: string, label: string, sort?: (a: any, b: any) => number, component?: any, width?: string}>}
     */
        columns: {
        key: string;
        label: string;
        sort?: (a: any, b: any) => number;
        component?: any;
        width?: string;
    }[];
        /** @description Callback to close the table */
        onClose: () => void;
    }

    let {
        items,
        itemsPerPage = 20,
        title,
        sortField,
        sortDirection,
        columns,
        onClose
    }: Props = $props();

    interface TableState {
        currentPage: number;
        sortField: string;
        sortDirection: "asc" | "desc";
    };

    const state: TableState = $state({
        currentPage: 1,
        sortField: sortField || "status",
        sortDirection: sortDirection || "asc",
    });

    /**
     * @description Sorts items based on specified field and direction
     * @param {(NemesisData | TestRun)[]} items - Array of items to sort
     * @param {string} field - Column key to sort by
     * @param {"asc" | "desc"} direction - Sort direction
     * @returns {(NemesisData | TestRun)[]} Sorted array
     */
    function sortItems(items: (NemesisData | TestRun)[], field: string, direction: "asc" | "desc") {
        const column = columns.find((c) => c.key === field);
        if (!column?.sort) return items;

        const sortFn = column.sort;

        return [...items].sort((a, b) => {
            const comparison = sortFn(a, b);
            return direction === "asc" ? comparison : -comparison;
        });
    }

    /**
     * @description Toggles sort direction for a given field
     * @param {string} field - Column key to sort by
     */
    function toggleSort(field: string) {
        state.sortField = field;
        state.sortDirection = state.sortField === field && state.sortDirection === "asc" ? "desc" : "asc";
    }

    /** @description Reactively sorted items based on current sort state */
    let sortedItems = $derived(sortItems(items, state.sortField, state.sortDirection));

    /** @description Reactively paginated items for current page */
    let paginatedItems = $derived(sortedItems.slice((state.currentPage - 1) * itemsPerPage, state.currentPage * itemsPerPage));

    /** @description Total number of pages based on items and itemsPerPage */
    let totalPages = $derived(Math.ceil(items.length / itemsPerPage));

    /**
     * @description Gets display value for an item property
     * @param {NemesisData | TestRun} item - Data item
     * @param {string} key - Property key
     * @returns {string} Stringified value or empty string
     */
    function getItemValue(item: NemesisData | TestRun, key: string): string {
        const value = (item as any)[key];
        return value !== undefined && value !== null ? String(value) : "";
    }
</script>

<div class="details mt-4">
    <div class="d-flex justify-content-between align-items-center mb-3">
        <h5>{title}</h5>
        <button class="btn btn-sm btn-outline-secondary" onclick={onClose}><i class="bi bi-x"></i> Close</button>
    </div>
    <div class="table-responsive">
        {#key sortedItems}
            <table class="table table-striped table-hover">
                <thead>
                    <tr>
                        {#each columns as column, i}
                            <th
                                class:sortable={column.sort !== undefined}
                                onclick={() => column.sort && toggleSort(column.key)}
                                title={column.label}
                                style={column.width
                                    ? `width: ${column.width}; min-width: ${column.width};`
                                    : i === columns.length - 1
                                    ? "width: auto; min-width: 150px;"
                                    : "width: 150px; min-width: 150px;"}
                            >
                                {column.label}
                                {#if column.sort && state.sortField === column.key}
                                    <i class="fas fa-sort-{state.sortDirection === 'desc' ? 'down' : 'up'}"></i>
                                {/if}
                            </th>
                        {/each}
                    </tr>
                </thead>
                <tbody>
                    {#each paginatedItems as item}
                        <tr>
                            {#each columns as column}
                                <td>
                                    {#if column.component}
                                        <column.component run={item} />
                                    {:else if column.key === "duration"}
                                        {item[column.key] === 0
                                            ? "unknown"
                                            : humanizeDuration(item[column.key] * 1000, { largest: 2, round: true })}
                                    {:else if column.key === "start_time"}
                                        <a href={`/tests/scylla-cluster-tests/${item.run_id}`} target="_blank"
                                            >{timestampToISODate(item[column.key] * 1000)}</a
                                        >
                                    {:else}
                                        {getItemValue(item, column.key) || ""}
                                    {/if}
                                </td>
                            {/each}
                        </tr>
                    {/each}
                </tbody>
            </table>
        {/key}
    </div>
    {#if totalPages > 1}
        <nav class="mt-3">
            <ul class="pagination pagination-sm justify-content-center">
                <li class="page-item {state.currentPage === 1 ? 'disabled' : ''}">
                    <button
                        class="page-link"
                        onclick={() => (state.currentPage -= 1)}
                        disabled={state.currentPage === 1}>Previous</button
                    >
                </li>
                {#each Array(totalPages) as _, i}
                    <li class="page-item {state.currentPage === i + 1 ? 'active' : ''}">
                        <button class="page-link" onclick={() => (state.currentPage = i + 1)}>{i + 1}</button>
                    </li>
                {/each}
                <li class="page-item {state.currentPage === totalPages ? 'disabled' : ''}">
                    <button
                        class="page-link"
                        onclick={() => (state.currentPage += 1)}
                        disabled={state.currentPage === totalPages}>Next</button
                    >
                </li>
            </ul>
        </nav>
    {/if}
</div>

<style>
    .details {
        border-top: 1px solid #dee2e6;
        padding-top: 1.5rem;
    }
    .sortable {
        cursor: pointer;
        position: relative;
        padding-right: 1.5rem;
    }
    .sortable:hover {
        background-color: rgba(0, 0, 0, 0.05);
    }
    .table {
        table-layout: fixed;
        width: 100%;
    }
    th,
    td {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
</style>
