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

    async function fetchTestResults(tid: string) {
        try {
            const params = queryString.stringify({testId: tid, startDate, endDate})
            const res = await fetch(`/api/v1/test-results?${params}`)
            if (res.status !== 200) throw `HTTP Error ${res.status}`
            const data = await res.json()
            if (data.status !== 'ok') throw `API Error: ${data.message}`
            graphs = data.response.graphs.map((g: any) => ({...g, id: generateRandomHash()}))
            ticks = data.response.ticks
            releasesFilters = Object.fromEntries(data.response.releases_filters.map((r: string) => [r, true]))
        } catch (e) {
            sendMessage('error', 'A backend error occurred', 'ResultsGraphs::fetchTestResults')
            console.log(e)
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


{#key graphs}
    <Filters {graphs} bind:filteredGraphs/>
{/key}
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
    .filters-container {
        display: flex;
        flex-direction: row;
        flex-wrap: wrap;
        margin-bottom: 20px
    }

    .input-group-inline {
        width: auto
    }

    .charts-container {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        align-items: center
    }

    .chart-container {
        display: flex;
        justify-content: center;
        align-items: center;
        margin: 10px
    }

    .big-size {
        width: 90%
    }

    .date-input {
        max-width: 130px
    }
</style>
