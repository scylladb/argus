<script lang="ts">
    import { sendMessage } from "../../../Stores/AlertStore";
    import ResultsGraph from "../../../TestRun/ResultsGraph.svelte";
    import GraphFilters from "../../../TestRun/Components/GraphFilters.svelte";
    import Filters from "../../../TestRun/Components/Filters.svelte";
    import queryString from "query-string";

    interface Props {
        settings?: any;
        testIds?: string[];
        dashboardObject: any;
    }

    let { settings = {}, testIds = [], dashboardObject }: Props = $props();

    let startDate = "";
    let endDate = "";
    let dateRange = $state(6);
    let width = 500;
    let height = 350;
    let releasesFilters = $state({});
    let testViews: Record<string, any[]> = $state({});
    let expandedTests = $state(new Set());
    let expandedViews = $state(new Set());
    let filteredGraphsByTest: Record<string, Record<string, any[]>> = $state({});
    let graphCounter = 0; // for chart id's
    let testsDetails: Record<string, any> = $state({});

    const generateGraphId = () => {
        graphCounter += 1;
        return graphCounter;
    };

    async function fetchGraphViews() {
        try {
            const params = {
                view_id: dashboardObject.id,
                start_date: startDate,
                end_date: endDate,
            };
            const queryStr = queryString.stringify(params);
            const res = await fetch(`/api/v1/views/widgets/graphs/graph_views?${queryStr}`);
            if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
            const data = await res.json();
            if (data.status !== "ok") throw new Error(data.message);

            testViews = data.response;
            testsDetails = data.tests_details;

            // Collect all unique releases from all tests
            const allReleases = new Set<string>();
            Object.values(data.response).forEach((testData: any) => {
                testData.forEach((testViewData: any) => {
                    if (testViewData.releases_filters) {
                        testViewData.releases_filters.forEach((release: string) => allReleases.add(release));
                    }
                });
            });

            // Initialize releases filters with all unique releases
            releasesFilters = Object.fromEntries(Array.from(allReleases).map((r: string) => [r, true]));

            graphCounter = 0;

            // Filter out tests without graph views and add unique IDs to graphs
            testViews = Object.fromEntries(
                Object.entries(data.response)
                    .filter(([_, views]) => views && views.length > 0)
                    .sort(([testIdA, viewsA], [testIdB, viewsB]) => {
                        const nameA = testsDetails[testIdA]?.name || testIdA;
                        const nameB = testsDetails[testIdB]?.name || testIdB;
                        return nameA.localeCompare(nameB);
                    })
                    .map(([testId, views]) => [
                        testId,
                        views.map((view) => ({
                            ...view,
                            graphs: view.graphs.map((graph) => ({
                                ...graph,
                                uniqueId: generateGraphId(),
                            })),
                        })),
                    ])
            );

            // Initialize filtered graphs for each test and view
            filteredGraphsByTest = {};
            Object.entries(testViews).forEach(([testId, views]) => {
                // Expand test by default
                expandedTests.add(testId);
                filteredGraphsByTest[testId] = {};
                views.forEach((view) => {
                    // Expand view by default
                    expandedViews.add(view.id);
                    filteredGraphsByTest[testId][view.id] = view.graphs;
                });
            });
            // Trigger reactivity
            expandedTests = expandedTests;
            expandedViews = expandedViews;
        } catch (e) {
            sendMessage("error", "Failed to fetch graph views", "GraphsWidget");
            console.error(e);
        }
    }

    function handleDateChange(event) {
        startDate = event.detail.startDate;
        endDate = event.detail.endDate;
        fetchGraphViews();
    }

    function handleReleaseChange() {
        // Trigger reactivity
        filteredGraphsByTest = filteredGraphsByTest;
    }

    function toggleTest(testId: string) {
        if (expandedTests.has(testId)) {
            expandedTests.delete(testId);
            // Also collapse all views under this test
            testViews[testId].forEach((view) => expandedViews.delete(view.id));
        } else {
            expandedTests.add(testId);
            // Also expand all views under this test
            testViews[testId].forEach((view) => expandedViews.add(view.id));
        }
        expandedTests = expandedTests; // Trigger reactivity
        expandedViews = expandedViews;
    }

    function toggleView(viewId: string) {
        if (expandedViews.has(viewId)) {
            expandedViews.delete(viewId);
        } else {
            expandedViews.add(viewId);
        }
        expandedViews = expandedViews;
    }

    function handleFilterChange(testId: string, viewId: string, filteredGraphs: any[]) {
        // Add unique IDs to filtered graphs if they don't have them
        filteredGraphsByTest[testId][viewId] = filteredGraphs.map((graph) => ({
            ...graph,
            uniqueId: graph.uniqueId || generateGraphId(),
        }));
        filteredGraphsByTest = filteredGraphsByTest; // Trigger reactivity
    }
</script>

<div class="container-fluid p-3">
    <GraphFilters
        bind:dateRange
        bind:releasesFilters
        on:dateChange={handleDateChange}
        on:releaseChange={handleReleaseChange}
    />

    {#if Object.keys(testViews).length === 0}
        <div class="alert alert-info text-center my-4">No graph views available. Add them in test's graphs window.</div>
    {:else}
        <div class="accordion" id="graphsAccordion">
            {#each Object.entries(testViews) as [testId, views]}
                <div class="card mb-3">
                    <div class="card-header bg-light" onclick={() => toggleTest(testId)}>
                        <h5 class="mb-0 d-flex align-items-center">
                            <i class="fas fa-chevron-{expandedTests.has(testId) ? 'down' : 'right'} me-2"></i>
                            <span>{testsDetails[testId]?.name || `Test ID: ${testId}`}</span>
                        </h5>
                    </div>

                    <div class="collapse {expandedTests.has(testId) ? 'show' : ''}" id="test-{testId}">
                        <div class="card-body">
                            {#each views as view}
                                <div class="card mb-3">
                                    <div class="card-header bg-transparent" onclick={() => toggleView(view.id)}>
                                        <div class="d-flex align-items-center">
                                            <i
                                                class="fas fa-chevron-{expandedViews.has(view.id)
                                                    ? 'down'
                                                    : 'right'} me-2"
></i>
                                            <h6 class="mb-0">{view.name}</h6>
                                        </div>
                                    </div>

                                    <div
                                        class="collapse {expandedViews.has(view.id) ? 'show' : ''}"
                                        id="view-{view.id}"
                                    >
                                        <div class="card-body">
                                            {#if view.description}
                                                <p class="text-muted mb-3">{view.description}</p>
                                            {/if}

                                            <Filters
                                                graphs={view.graphs}
                                                bind:filteredGraphs={filteredGraphsByTest[testId][view.id]}
                                                on:filterChange={() =>
                                                    handleFilterChange(
                                                        testId,
                                                        view.id,
                                                        filteredGraphsByTest[testId][view.id]
                                                    )}
                                            />
                                            <div class="charts-container">
                                                {#key filteredGraphsByTest[testId][view.id]}
                                                    {#each filteredGraphsByTest[testId][view.id] as graph (graph.uniqueId)}
                                                        <div class="chart-container"
                                                             class:big-size={filteredGraphsByTest[testId][view.id].length < 2}>
                                                            <ResultsGraph
                                                                {graph}
                                                                index={graph.uniqueId}
                                                                ticks={view.ticks}
                                                                {releasesFilters}
                                                                height={filteredGraphsByTest[testId][view.id].length === 1
                                                                    ? 600
                                                                    : height}
                                                                width={filteredGraphsByTest[testId][view.id].length === 1
                                                                    ? 1000
                                                                    : width}
                                                                test_id={testId}
                                                            />
                                                        </div>
                                                    {/each}
                                                {/key}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            {/each}
                        </div>
                    </div>
                </div>
            {/each}
        </div>
    {/if}
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
        position: relative;
        width: 520px; /* Fixed width to ensure proper wrapping */
    }

    .big-size {
        width: 90%;
    }

    :global(.card-header) {
        cursor: pointer;
    }

    :global(.card-header:hover) {
        background-color: var(--bs-gray-200) !important;
    }
</style>
