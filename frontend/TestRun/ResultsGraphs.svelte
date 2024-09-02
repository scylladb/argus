<script>
    import {createEventDispatcher, onMount} from "svelte";
    import {sendMessage} from "../Stores/AlertStore";
    import ResultsGraph from "./ResultsGraph.svelte";

    export let test_id = "";
    let graphs = [];
    let tableFilters = [];
    let columnFilters = [];
    let selectedTableFilters = [];
    let selectedColumnFilters = [];
    let filteredGraphs = [];
    let width = 500;  // default width for each chart
    let height = 300;  // default height for each chart
    const dispatch = createEventDispatcher();

    const dispatch_run_click = (e) => {
        dispatch("runClick", {runId: e.detail.runId});
    };

    const fetchTestResults = async function (testId) {
        try {
            let res = await fetch(`/api/v1/test-results?testId=${testId}`);
            if (res.status != 200) {
                return Promise.reject(`HTTP Error ${res.status} trying to fetch test results`);
            }
            let results = await res.json();
            if (results.status != "ok") {
                return Promise.reject(`API Error: ${results.message}, while trying to fetch test results`);
            }
            graphs = results["response"].map((graph) => ({...graph, id: generateRandomHash()}));
            extractTableFilters();
            extractColumnFilters();
            filterGraphs();
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching test run data.\nMessage: ${error.response.arguments[0]}`,
                    "ResultsGraphs::fetchTestResults"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test results data fetch",
                    "ResultsGraphs::fetchTestResults"
                );
                console.log(error);
            }
        }
    };

    const generateRandomHash = () => {
        return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    };

    const extractTableFilters = () => {
        let fltrs = new Map();
        graphs.forEach(graph => {
            const title = graph.options.plugins.title.text;
            const parts = title.split("-").slice(0, -1);
            parts.forEach((part, index) => {
                const level = index + 1;
                if (!fltrs.has(level)) {
                    fltrs.set(level, new Set());
                }
                fltrs.get(level).add(part.trim());
            });
        });
        tableFilters = Array.from(fltrs.entries()).sort((a, b) => a[0] - b[0]).map(entry => ({
            level: entry[0],
            items: Array.from(entry[1])
        }));
    };

    const extractColumnFilters = () => {
        let fltrs = new Set();
        graphs.forEach(graph => {
            const title = graph.options.plugins.title.text;
            const parts = title.split("-").slice(-1);
            parts.forEach(part => {
                fltrs.add(part.trim());
            });
        });
        columnFilters = Array.from(fltrs);
    };

    const toggleTableFilter = (filterName, level) => {
        const currentFilter = selectedTableFilters.find(f => f.level === level);
        if (currentFilter && currentFilter.name === filterName) {
            selectedTableFilters = selectedTableFilters.filter(f => f.level !== level);
        } else {
            selectedTableFilters = [
                ...selectedTableFilters.filter(f => f.level !== level),
                {name: filterName, level}
            ];
        }
        filterGraphs();
    };

    const toggleColumnFilter = (filterName) => {
        if (selectedColumnFilters.includes(filterName)) {
            selectedColumnFilters = selectedColumnFilters.filter(f => f !== filterName);
        } else {
            selectedColumnFilters = [...selectedColumnFilters, filterName];
        }
        filterGraphs();
    };

    const filterGraphs = () => {
        if (selectedTableFilters.length === 0 && selectedColumnFilters.length === 0) {
            filteredGraphs = graphs.map(graph => ({...graph, id: generateRandomHash()}));
        } else {
            filteredGraphs = graphs
                .filter(graph => {
                    const title = graph.options.plugins.title.text;
                    const parts = title.split("-").map(part => part.trim());
                    const matchesTableFilters = selectedTableFilters.every(filter => parts.includes(filter.name));
                    const matchesColumnFilters = selectedColumnFilters.length === 0
                        || selectedColumnFilters.some(filter => parts.includes(filter));
                    return matchesTableFilters && matchesColumnFilters;
                })
                .map(graph => ({...graph, id: generateRandomHash()}));
        }
    };

    const getTableFilterColor = (level) => {
        const intermediateColors = ["#ff7f7f", "#7fbfff", "#ffbf7f", "#bf7fff", "#ffff7f", "#7fffff", "#bf7f7f"];
        return intermediateColors[level % intermediateColors.length];
    };

    onMount(() => {
        fetchTestResults(test_id);
    });
</script>

<div class="filters-container">
    {#each tableFilters as filterGroup}
        {#each filterGroup.items as filter}
            <button
                    on:click={() => toggleTableFilter(filter, filterGroup.level)}
                    class:selected={selectedTableFilters.some(f => f.name === filter)}
                    style="background-color: {getTableFilterColor(filterGroup.level)}"
            >
                {filter}
            </button>
        {/each}
    {/each}
    {#each columnFilters as filter}
        <button
                on:click={() => toggleColumnFilter(filter)}
                class:selected={selectedColumnFilters.some(f => f === filter)}
                style="background-color: #7fff7f"
        >
            {filter}
        </button>
    {/each}
    <button on:click={() => { selectedTableFilters = []; selectedColumnFilters = []; filterGraphs(); }}>Show All</button>
</div>

<div class="charts-container">
    {#each filteredGraphs as graph (graph.id)}
        <div class="chart-container {filteredGraphs.length<3? 'big-size': ''}">
            <ResultsGraph {graph} {width} {height} test_id={test_id} index={graph.id} on:runClick={dispatch_run_click}/>
        </div>
    {/each}
</div>

<style>
    .charts-container {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        align-items: center;
    }

    .chart-container {
        display: flex;
        justify-content: center;
        align-items: center;
        margin: 10px;
    }

    .big-size {
        width: 45%;
    }

    .filters-container {
        display: flex;
        justify-content: center;
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
