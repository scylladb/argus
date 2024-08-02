<script>
    import {createEventDispatcher, onMount} from "svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import ResultsGraph from "./ResultsGraph.svelte";

    export let test_id = "";
    let graphs = [];
    let allFilters = [];
    let filters = [];
    let selectedFilters = [];
    let filteredGraphs = [];
    let width = 500;  // default width for each chart
    let height = 300;  // default height for each chart
    const dispatch = createEventDispatcher();

    const dispatch_run_click = (e) => {
        dispatch("runClick", { runId: e.detail.runId });
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
            graphs = results["response"].map((graph) => ({ ...graph, id: generateRandomHash() }));
            extractFilters();
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

    const extractFilters = () => {
        let fltrs = new Map();
        graphs.forEach(graph => {
            const title = graph.options.plugins.title.text;
            const parts = title.split("-");
            parts.forEach((part, index) => {
                const level = index === parts.length - 1 ? 7 : index + 1;
                if (!fltrs.has(level)) {
                    fltrs.set(level, new Set());
                }
                fltrs.get(level).add(part.trim());
            });
        });
        allFilters = Array.from(fltrs.entries()).sort((a, b) => a[0] - b[0]).map(entry => ({
            level: entry[0],
            items: Array.from(entry[1])
        }));
        filters = [...allFilters];
    };

    const toggleFilter = (filterName, level) => {
        const currentFilter = selectedFilters.find(f => f.level === level);
        if (currentFilter && currentFilter.name === filterName) {
            selectedFilters = selectedFilters.filter(f => f.level !== level);
        } else {
            selectedFilters = selectedFilters.filter(f => f.level !== level);
            selectedFilters = [...selectedFilters, { name: filterName, level }];
        }
        filterGraphs();
        updateAvailableFilters();
    };

    const filterGraphs = () => {
        if (selectedFilters.length === 0) {
            filteredGraphs = graphs.map(graph => ({ ...graph, id: generateRandomHash() }));
        } else {
            filteredGraphs = graphs
                .filter(graph => {
                    const title = graph.options.plugins.title.text;
                    const parts = title.split("-").map(part => part.trim());
                    return selectedFilters.every(filter => parts.includes(filter.name));
                })
                .map(graph => ({ ...graph, id: generateRandomHash() }));
        }
    };

    const updateAvailableFilters = () => {
        let applicableFilters = new Map();
        filteredGraphs.forEach(graph => {
            const title = graph.options.plugins.title.text;
            const parts = title.split("-");
            parts.forEach((part, index) => {
                const level = index === parts.length - 1 ? 7 : index + 1;
                if (!applicableFilters.has(level)) {
                    applicableFilters.set(level, new Set());
                }
                applicableFilters.get(level).add(part.trim());
            });
        });

        filters = allFilters.map(filterGroup => ({
            level: filterGroup.level,
            items: filterGroup.items.filter(item =>
                applicableFilters.has(filterGroup.level) && applicableFilters.get(filterGroup.level).has(item)
            )
        }));

        // Remove lower level filters if they become inapplicable
        selectedFilters = selectedFilters.filter(filter =>
            filters.some(group =>
                group.level === filter.level &&
                group.items.includes(filter.name)
            )
        );
    };

    const getFilterColor = (level) => {
        const firstColor = "#ff7f7f";
        const lastColor = "#7fff7f";
        const intermediateColors = ["#7fbfff", "#ffbf7f", "#bf7fff", "#ffff7f", "#7fffff", "#bf7f7f"];

        if (level === 1) {
            return firstColor;
        } else if (level === 7) {
            return lastColor;
        } else {
            return intermediateColors[(level - 2) % intermediateColors.length];
        }
    };

    onMount(() => {
        fetchTestResults(test_id);
    });
</script>

<div class="filters-container">
    {#each filters as filterGroup}
        {#each filterGroup.items as filter}
            <button
                    on:click={() => toggleFilter(filter, filterGroup.level)}
                    class:selected={selectedFilters.some(f => f.name === filter)}
                    style="background-color: {getFilterColor(filterGroup.level)}"
            >
                {filter}
            </button>
        {/each}
    {/each}
    <button on:click={() => { selectedFilters = []; filterGraphs(); updateAvailableFilters(); }}>Show All</button>
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
        width: 50%;
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
