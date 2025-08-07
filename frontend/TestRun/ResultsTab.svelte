<script lang="ts">
    import {onMount} from "svelte";
    import ScreenshotModal from "./Components/ScreenshotModal.svelte";
    import ResultTable from "./Components/ResultTable.svelte";
    import Fa from "svelte-fa";
    import { faMarkdown } from "@fortawesome/free-brands-svg-icons";

    let fetching = $state(true);
    interface Props {
        id?: string;
        test_id?: string;
    }

    let { id = "", test_id = "" }: Props = $props();
    let results = {};
    let filters = $state([]);
    let selectedFilters = $state([]);
    let filteredTables = $state({});
    let selectedScreenshot = $state("");
    let showFilters = $state(false);
    let resultTables = $state({});

    const fetchResults = async function () {
        fetching = true;
        try {
            let apiResponse = await fetch(`/api/v1/run/${test_id}/${id}/fetch_results`);
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                fetching = false;
                results = apiJson.tables.reduce((acc, item) => {
                    const table_name = Object.keys(item)[0];
                    acc[table_name] = item[table_name];
                    return acc;
                }, {});
                extractFilters();
                filterTables();
            }
        } catch (error) {
            console.log(error);
        }
    };

    const copyAllTablesAsMarkdown = async function () {
        const markdownTables = await Promise.all(Object.entries(resultTables).map(async ([tableName, table]) => `### ${tableName}\n` + await table.copyResultTableAsMarkdown("string")));
        await navigator.clipboard.writeText(markdownTables.join("\n"));
    };

    const extractFilters = () => {
        // Extract filters from the table names by splitting by "-" and grouping by level
        let fltrs = new Map();
        Object.keys(results).forEach(name => {
            const parts = name.split("-");
            parts.forEach((part, index) => {
                const level = index + 1;
                if (!fltrs.has(level)) {
                    fltrs.set(level, new Set());
                }
                fltrs.get(level).add(part.trim());
            });
        });

        filters = Array.from(fltrs.entries())
            .sort(([left], [right]) => left - right)
            .map(([level, items]) => ({
                level,
                items: Array.from(items)
            }))
            .filter(entry => entry.items.length > 1);  // Filter out filters with only one item

        // Show filters only if any group contains at least 2 filters
        showFilters = filters.some(entry => entry.items.length >= 2);
    };

    const toggleFilter = (filterName, level) => {
        // Toggle filter by level - one filter per level can be applied
        const currentFilter = selectedFilters.find(f => f.level === level);
        if (currentFilter && currentFilter.name === filterName) {
            selectedFilters = selectedFilters.filter(f => f.level !== level);
        } else {
            selectedFilters = selectedFilters.filter(f => f.level !== level);
            selectedFilters = [...selectedFilters, {name: filterName, level}];
        }
        filterTables();
    };

    const filterTables = () => {
        // Filter tables by selected filters - only tables that contain all selected filters are shown
        const filteredTableNames = Object.keys(results)
            .filter(title => {
                const parts = title.split("-").map(part => part.trim());
                return selectedFilters.every(filter => parts.includes(filter.name));
            });
        filteredTables = filteredTableNames.reduce((obj, key) => {
            obj[key] = results[key];
            return obj;
        }, {});
    };

    const getFilterColor = (level) => {
        const filterColors = ["#7fbfff", "#ff7f7f", "#ffbf7f", "#bf7fff", "#bf7f7f", "#7fffff", "#ffff7f"];
        return filterColors[(level - 2) % filterColors.length];
    };

    onMount(() => {
        fetchResults();
    });
</script>

<style>
    ul.result-list {
        list-style-type: none;
        padding: 0;
        margin: 0;
        overflow-x: auto;
        white-space: nowrap;
        display: block;
    }

    .filters-container {
        display: flex;
        justify-content: flex-start;
        align-items: center;
        margin-bottom: 20px;
        flex-wrap: wrap;
    }

    .filters-container button {
        margin: 5px;
        padding: 10px 15px;
        cursor: pointer;
        border: none;
        border-radius: 5px;
    }

    .filters-container button:hover {
        background-color: #e0e0e0;
    }

    .filters-container button.selected {
        border: 2px solid #333;
    }
</style>

{#if !fetching}
    <div class="p-2">
        <div class="filters-container" class:d-none={!showFilters}>
            <button onclick={() => { selectedFilters = []; filterTables();  }}>Show All</button>
            {#each filters as filterGroup}
                {#each filterGroup.items as filter}
                    <button
                            onclick={() => toggleFilter(filter, filterGroup.level)}
                            class:selected={selectedFilters.some(f => f.name === filter)}
                            style="background-color: {getFilterColor(filterGroup.level)}"
                    >
                        {filter}
                    </button>
                {/each}
            {/each}
        </div>
        <div class="mb-2">
            <button class="btn btn-sm btn-primary" onclick={() => copyAllTablesAsMarkdown()}><Fa icon={faMarkdown}/> Copy all tables as Markdown</button>
        </div>
        <ul class="result-list">
            {#each Object.entries(filteredTables) as [table_name, result]}
                <ResultTable
                    bind:this={resultTables[table_name]}
                    table_name={table_name}
                    result={result}
                    test_id={test_id}
                    bind:selectedScreenshot
                />
            {/each}
        </ul>
    </div>
    <ScreenshotModal bind:selectedScreenshot/>
{:else}
    <div class="mb-2 text-center p-2">
        <span class="spinner-border spinner-border-sm"></span> Loading results...
    </div>
{/if}
