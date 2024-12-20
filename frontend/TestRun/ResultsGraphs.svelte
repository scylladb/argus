<script lang="ts">
    import {onMount, createEventDispatcher} from 'svelte'
    import dayjs from 'dayjs'
    import queryString from 'query-string'
    import {sendMessage} from '../Stores/AlertStore'
    import ResultsGraph from './ResultsGraph.svelte'
    import Filters from './Components/Filters.svelte'

    export let test_id = ''
    let graphs: any[] = []
    let filteredGraphs: any[] = []
    let releasesFilters: Record<string, boolean> = {}
    let ticks: Record<string, any> = {}
    let width = 500
    let height = 300
    let startDate = ''
    let endDate = ''
    let dateRange = 6
    let showCustomInputs = false
    const dispatch = createEventDispatcher()
    const dispatch_run_click = (e: CustomEvent<{ runId: string }>) => {
        dispatch('runClick', {runId: e.detail.runId})
    }
    onMount(() => setDateRange(dateRange))

    function setDateRange(months: number) {
        if (months === -1) {
            startDate = '';
            endDate = '';
            showCustomInputs = true;
            return
        }
        dateRange = months
        const now = dayjs()
        endDate = now.format('YYYY-MM-DD')
        startDate = now.subtract(months, 'month').format('YYYY-MM-DD')
        showCustomInputs = false
        fetchTestResults(test_id)
    }

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
    }

    function generateRandomHash() {
        return Math.random().toString(36).slice(2, 15) + Math.random().toString(36).slice(2, 15)
    }

    function toggleReleaseFilter(r: string) {
        releasesFilters[r] = !releasesFilters[r]
        filteredGraphs = [...filteredGraphs]
    }
</script>

<div class="filters-container">
    <span class="my-auto">Time range:</span>
    <div class="input-group input-group-inline input-group-sm mx-2">
        <button class="btn btn-outline-primary btn-sm" class:active={dateRange===1} on:click={()=>setDateRange(1)}>Last Month</button>
        <button class="btn btn-outline-primary btn-sm" class:active={dateRange===3} on:click={()=>setDateRange(3)}>Last 3 Months</button>
        <button class="btn btn-outline-primary btn-sm" class:active={dateRange===6} on:click={()=>setDateRange(6)}>Last 6 Months</button>
        <button class="btn btn-outline-primary btn-sm" class:active={dateRange===12} on:click={()=>setDateRange(12)}>Last year</button>
        <button class="btn btn-outline-primary btn-sm" class:active={dateRange===24} on:click={()=>setDateRange(24)}>Last 2 years</button>
        <button class="btn btn-outline-primary btn-sm" class:active={showCustomInputs} on:click={()=>setDateRange(-1)}>Custom</button>
        {#if showCustomInputs}
            <input type="date" class="form-control date-input" bind:value={startDate} on:change={()=>fetchTestResults(test_id)}/>
            <input type="date" class="form-control date-input" bind:value={endDate} on:change={()=>fetchTestResults(test_id)}/>
        {/if}
    </div>
    <span class="my-auto">Releases:</span>
    <div class="input-group input-group-inline input-group-sm mx-2">
        {#each Object.keys(releasesFilters) as r}
            <button class="btn btn-sm btn-outline-dark" on:click={()=>toggleReleaseFilter(r)} class:active={releasesFilters[r]}>
                {r}
            </button>
        {/each}
    </div>
</div>

{#key graphs}
    <Filters {graphs} bind:filteredGraphs/>
{/key}
<div class="charts-container">
    {#key filteredGraphs}
        {#each filteredGraphs as graph (graph.id)}
            <div class="chart-container" class:big-size={filteredGraphs.length<2}>
                <ResultsGraph
                        {graph} {ticks}
                        height={filteredGraphs.length===1?600:height}
                        width={filteredGraphs.length===1?1000:width}
                        test_id={test_id}
                        index={graph.id}
                        releasesFilters={releasesFilters}
                        on:runClick={dispatch_run_click}
                />
            </div>
        {/each}
    {/key}
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
