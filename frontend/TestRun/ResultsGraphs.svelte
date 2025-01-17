<script>
    import {createEventDispatcher, onMount} from "svelte";
    import {sendMessage} from "../Stores/AlertStore";
    import ResultsGraph from "./ResultsGraph.svelte";
    import GraphFilters from "./Components/GraphFilters.svelte";
    import dayjs from "dayjs";
    import queryString from "query-string";

    export let test_id = "";
    let graphs = [];
    let ticks = {};
    let releasesFilters = {};
    let tableFilters = [];
    let columnFilters = [];
    let selectedTableFilters = [];
    let selectedColumnFilters = [];
    let filteredGraphs = [];
    let startDate = "";
    let endDate = "";
    let dateRange = 6;
    let showCustomInputs = false;
    let width = 500;  // default width for each chart
    let height = 350;  // default height for each chart

    const dispatch = createEventDispatcher();

    const dispatchRunClick = (e) => {
        dispatch("runClick", {runId: e.detail.runId});
    };

    const fetchTestResults = async function (testId) {
        try {
            const params = queryString.stringify({testId, startDate, endDate});
            let res = await fetch(`/api/v1/test-results?${params}`);
            if (res.status != 200) {
                return Promise.reject(`HTTP Error ${res.status} trying to fetch test results`);
            }
            let results = await res.json();
            if (results.status != "ok") {
                return Promise.reject(`API Error: ${results.message}, while trying to fetch test results`);
            }
            const response = results["response"];
            graphs = response["graphs"].map((graph) => ({...graph, id: generateRandomHash()}));
            ticks = response["ticks"];
            releasesFilters = Object.fromEntries(response["releases_filters"].map(key => [key, true]));
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

    const handleDateChange = (event) => {
        startDate = event.detail.startDate;
        endDate = event.detail.endDate;
        fetchTestResults(test_id);
    };

    const handleReleaseChange = () => {
        filterGraphs();
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
        const intermediateColors = [
            "#B8EFFF",
            "#FECBA1",
            "#D6B3E6",
            "#FFE699",
            "#F0A5C5",
            "#C4C8CA",
        ];
        return intermediateColors[level - 1 % intermediateColors.length];
    };

    const toggleReleaseFilter = (filterName) => {
        releasesFilters[filterName] = !releasesFilters[filterName];
        filterGraphs();
    };

    onMount(() => {
        // setDefaultDateRange();
        // fetchTestResults(test_id);
    });
</script>

<GraphFilters
        bind:dateRange
        bind:releasesFilters
        on:dateChange={handleDateChange}
        on:releaseChange={handleReleaseChange}
/>

<span>Filters:</span>
<div class="filters-container  ">
    <div class="input-group input-group-inline input-group-sm mx-1">
        <button class="btn btn-outline-dark colored"
                on:click={() => { selectedTableFilters = []; filterGraphs(); }}>X
        </button>
    </div>
    {#each tableFilters as filterGroup}
        <div class="input-group input-group-inline  input-group-sm mx-1">
            {#each filterGroup.items as filter}
                <button class="btn btn-outline-dark colored"
                        on:click={() => toggleTableFilter(filter, filterGroup.level)}
                        class:selected={selectedTableFilters.some(f => f.name === filter)}
                        style="background-color: {getTableFilterColor(filterGroup.level)}"
                >
                    {filter}
                </button>
            {/each}
        </div>

    {/each}
</div>
<span>Metrics:</span>
<div class="filters-container  ">
    <div class="input-group input-group-inline  input-group-sm mx-1">
        <button class="btn btn-outline-dark colored"
                on:click={() => { selectedColumnFilters = []; filterGraphs(); }}>X
        </button>
    </div>
    <div class="input-group input-group-inline  input-group-sm mx-1">
        {#each columnFilters as filter}
            <button class="btn btn-outline-dark colored"
                    on:click={() => toggleColumnFilter(filter)}
                    class:selected={selectedColumnFilters.some(f => f === filter)}
                    style="background-color: #a3e2cc"
            >
                {filter}
            </button>
        {/each}
    </div>
</div>
<div class="charts-container">
    {#each filteredGraphs as graph (graph.id)}
        <div class="chart-container"
             class:big-size={filteredGraphs.length < 2}>
            <ResultsGraph
                    {graph}
                    {ticks}
                    height={filteredGraphs.length === 1 ? 600 : height}
                    width={filteredGraphs.length === 1 ? 1000 : width}
                    test_id={test_id}
                    index={graph.id}
                    releasesFilters={releasesFilters}
                    on:runClick={dispatchRunClick}
            />
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
        width: 90%;
    }

    .filters-container {
        display: flex;
        flex-direction: row;
        justify-content: flex-start;
        align-content: flex-start;
        margin-bottom: 20px;
        flex-wrap: wrap;
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
