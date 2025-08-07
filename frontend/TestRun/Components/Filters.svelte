<script lang="ts">
    import {onMount} from 'svelte';

    interface Props {
        graphs?: any[];
        filteredGraphs?: any[];
    }

    let { graphs = [], filteredGraphs = $bindable([]) }: Props = $props();
    let tableFilters: { level: number; items: string[] }[] = $state([]);
    let columnFilters: string[] = $state([]);
    let selectedTableFilters: { name: string; level: number }[] = $state([]);
    let selectedColumnFilters: string[] = $state([]);

    function extractTableFilters() {
        let fltrs = new Map<number, Set<string>>();
        for (let g of graphs) {
            const parts = g.options.plugins.title.text.split("-").slice(0, -1).map(p => p.trim());
            parts.forEach((p, i) => {
                const lvl = i + 1;
                if (!fltrs.has(lvl)) fltrs.set(lvl, new Set());
                fltrs.get(lvl)?.add(p);
            });
        }
        tableFilters = [...fltrs.entries()]
            .sort((a, b) => a[0] - b[0])
            .map(([level, items]) => ({level, items: [...items]}));
    }

    function extractColumnFilters() {
        let fltrs = new Set<string>();
        for (let g of graphs) {
            const parts = g.options.plugins.title.text.split("-").slice(-1).map(p => p.trim());
            parts.forEach(p => fltrs.add(p));
        }
        columnFilters = [...fltrs];
    }

    function toggleTableFilter(filter: string, level: number) {
        const existing = selectedTableFilters.find(f => f.level === level);
        if (existing && existing.name === filter) {
            selectedTableFilters = selectedTableFilters.filter(f => f.level !== level);
        } else {
            selectedTableFilters = [...selectedTableFilters.filter(f => f.level !== level), {name: filter, level}];
        }
        filterTables();
    }

    function toggleColumnFilter(filter: string) {
        selectedColumnFilters = selectedColumnFilters.includes(filter)
            ? selectedColumnFilters.filter(f => f !== filter)
            : [...selectedColumnFilters, filter];
        filterTables();
    }

    function filterTables() {
        if (!selectedTableFilters.length && !selectedColumnFilters.length) {
            filteredGraphs = graphs;
            return;
        }
        filteredGraphs = graphs.filter(g => {
            const parts = g.options.plugins.title.text.split("-").map(p => p.trim());
            const matchTable = selectedTableFilters.every(f => parts.includes(f.name));
            const matchCol = !selectedColumnFilters.length || selectedColumnFilters.some(f => parts.includes(f));
            return matchTable && matchCol;
        });
    }

    function clearTableFilters() {
        selectedTableFilters = [];
        filterTables();
    }

    function clearColumnFilters() {
        selectedColumnFilters = [];
        filterTables();
    }

    function getTableFilterColor(level: number) {
        const colors = ["#B8EFFF", "#FECBA1", "#D6B3E6", "#FFE699", "#F0A5C5", "#C4C8CA"];
        return colors[(level - 1) % colors.length];
    }

    onMount(() => {
        extractTableFilters();
        extractColumnFilters();
        filterTables();
    });
</script>

<span>Filters:</span>
<div class="filters-container">
    <div class="input-group input-group-inline input-group-sm mx-1">
        <button class="btn btn-outline-dark colored" onclick={clearTableFilters}>X</button>
    </div>
    {#each tableFilters as group}
        <div class="input-group input-group-inline input-group-sm mx-1">
            {#each group.items as filter}
                <button
                        class="btn btn-outline-dark colored"
                        onclick={()=>toggleTableFilter(filter,group.level)}
                        class:selected={selectedTableFilters.some(f=>f.name===filter)}
                        style="background-color:{getTableFilterColor(group.level)}">
                    {filter}
                </button>
            {/each}
        </div>
    {/each}
</div>

<span>Metrics:</span>
<div class="filters-container">
    <div class="input-group input-group-inline input-group-sm mx-1">
        <button class="btn btn-outline-dark colored" onclick={clearColumnFilters}>X</button>
    </div>
    <div class="input-group input-group-inline input-group-sm mx-1">
        {#each columnFilters as filter}
            <button
                    class="btn btn-outline-dark colored"
                    onclick={()=>toggleColumnFilter(filter)}
                    class:selected={selectedColumnFilters.includes(filter)}
                    style="background-color: #a3e2cc">
                {filter}
            </button>
        {/each}
    </div>
</div>

<style>
    .filters-container {
        display: flex;
        flex-direction: row;
        flex-wrap: wrap;
        margin-bottom: 20px
    }

    .input-group-inline {
        width: auto;
    }

    button.colored:not(.selected):not(:hover) {
        background-color: #f0f0f0 !important;
    }

    .date-input {
        max-width: 200px;
    }
</style>
