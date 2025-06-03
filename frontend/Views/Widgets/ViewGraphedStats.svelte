<script lang="ts">
    import { onMount } from "svelte";
    import { writable, derived } from "svelte/store";
    import Chart from "chart.js/auto";
    import type { Chart as ChartType } from "chart.js/auto";
    import NemesisTable from "./ViewGraphedStats/NemesisTable.svelte";
    import TestRunTable from "./ViewGraphedStats/TestRunTable.svelte";
    import Filters from "./ViewGraphedStats/Filters.svelte";
    import { TestRun, NemesisData, DataResponse } from "./ViewGraphedStats/Interfaces";

    export let dashboardObject: { id: string };
    export let settings: {testFilters: string[]} ;

    /**
     * @description Reactive state store containing component data and UI states
     * @type {import('svelte/store').Writable}
     */
    const state = writable<{
        loading: boolean;
        errorMsg: string;
        collapsed: boolean;
        allData: DataResponse;
        filteredData: DataResponse;
        currentBuildLevel: string;
        selectedNemesis: string | null;
        selectedFilter: string;
    }>({
        loading: true,
        errorMsg: "",
        collapsed: true,
        allData: { test_runs: [], nemesis_data: [] },
        filteredData: { test_runs: [], nemesis_data: [] },
        currentBuildLevel: "",
        selectedNemesis: null,
        selectedFilter: "",
    });

    /**
     * @description Store for Chart.js instances
     * @type {import('svelte/store').Writable<Record<string, ChartType>>}
     */
    const charts = writable<Record<string, ChartType>>({});

    /**
     * @description Store for computed statistics
     * @type {import('svelte/store').Writable}
     */
    const stats = writable({
        totalDuration: 0,
        uniqueTests: 0,
        uniqueNemesisCount: 0,
        nemesisStats: { totalCount: 0, succeeded: 0, failed: 0, totalDuration: 0, uniqueTypes: 0 },
    });

    /**
     * @description Derived store to determine if current build level is a leaf node
     * @type {import('svelte/store').Readable<boolean>}
     */
    const isLeafNode = derived(state, ($state) => {
        if (!$state.currentBuildLevel) return false;
        return !$state.allData.test_runs.some(
            (run) =>
                run.build_id.startsWith($state.currentBuildLevel + "/") && run.build_id !== $state.currentBuildLevel
        );
    });

    let chartCanvas: HTMLCanvasElement;
    let buildChartCanvas: HTMLCanvasElement;
    let nemesisChartCanvas: HTMLCanvasElement;
    let nemesisStatsCanvas: HTMLCanvasElement;

    /**
     * @description Fetches data from the API and updates state
     * @async
     */
    async function fetchData() {
        $state.loading = true;
        $state.errorMsg = "";
        try {
            // Prepare filters if they exist
            const filters = settings.testFilters && settings.testFilters.length > 0
                ? `&filters=${encodeURIComponent(JSON.stringify(settings.testFilters))}`
                : '';

            const response = await fetch(`/api/v1/views/widgets/graphed_stats?view_id=${dashboardObject.id}${filters}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            if (data.status === "error") throw new Error(data.response.exception);

            $state.allData = data.response || { test_runs: [], nemesis_data: [] };
            applyFilter($state.selectedFilter);
        } catch (error) {
            $state.errorMsg = `Failed to load graphed stats: ${(error as Error).message}`;
        } finally {
            $state.loading = false;
        }
    }

    /**
     * @description Applies version filter to data
     * @param {string} filter - Version filter string
     */
    function applyFilter(filter: string) {
        $state.selectedFilter = filter;
        $state.filteredData = {
            test_runs: $state.allData.test_runs.filter((run) => (filter ? run.version.startsWith(filter) : true)),
            nemesis_data: $state.allData.nemesis_data.filter((n) => (filter ? n.version.startsWith(filter) : true)),
        };
        $state.currentBuildLevel = "";
        $state.selectedNemesis = null;
        updateStatsAndCharts();
    }

    /**
     * @description Filters data by build level hierarchy
     * @param {string} buildPrefix - Build level prefix to filter by
     */
    function filterByBuildLevel(buildPrefix: string) {
        $state.currentBuildLevel = buildPrefix;
        const hasChildren = $state.allData.test_runs.some(
            (run) => run.build_id.startsWith(buildPrefix + "/") && run.build_id !== buildPrefix
        );

        $state.filteredData = {
            test_runs: $state.allData.test_runs.filter(
                (run) =>
                    ($state.selectedFilter ? run.version.startsWith($state.selectedFilter) : true) &&
                    (buildPrefix
                        ? hasChildren
                            ? run.build_id.startsWith(buildPrefix)
                            : run.build_id === buildPrefix
                        : true)
            ),
            nemesis_data: $state.allData.nemesis_data.filter(
                (n) =>
                    ($state.selectedFilter ? n.version.startsWith($state.selectedFilter) : true) &&
                    (buildPrefix
                        ? hasChildren
                            ? n.build_id.startsWith(buildPrefix)
                            : n.build_id === buildPrefix
                        : true)
            ),
        };

        if ($state.filteredData.test_runs.length === 0 && !hasChildren) {
            $state.filteredData = {
                test_runs: $state.allData.test_runs.filter(
                    (run) =>
                        ($state.selectedFilter ? run.version.startsWith($state.selectedFilter) : true) &&
                        (buildPrefix ? run.build_id.startsWith(buildPrefix) : true)
                ),
                nemesis_data: $state.allData.nemesis_data.filter(
                    (n) =>
                        ($state.selectedFilter ? n.version.startsWith($state.selectedFilter) : true) &&
                        (buildPrefix ? n.build_id.startsWith(buildPrefix) : true)
                ),
            };
        }

        $state.selectedNemesis = null;
        updateStatsAndCharts();
    }

    /**
     * @description Safely destroys a chart instance if it exists
     * @param {string} chartName - Name of the chart to destroy
     */
    function safeDestroyChart(chartName: string) {
        if ($charts[chartName]) {
            $charts[chartName].destroy();
        }
    }

    /**
     * @description Updates statistics and recreates charts
     */
    function updateStatsAndCharts() {
        $stats.totalDuration = $state.filteredData.test_runs.reduce((sum, run) => sum + Math.max(0, run.duration), 0);
        $stats.uniqueTests = new Set($state.filteredData.test_runs.map((run) => run.build_id)).size;
        $stats.uniqueNemesisCount = new Set($state.filteredData.nemesis_data.map((n) => n.name)).size;

        const nemStats = $state.filteredData.nemesis_data.reduce(
            (acc, n) => {
                acc.totalDuration += Math.max(0, n.duration);
                acc[n.status === "succeeded" ? "succeeded" : "failed"]++;
                return acc;
            },
            { succeeded: 0, failed: 0, totalDuration: 0 }
        );

        $stats.nemesisStats = {
            ...nemStats,
            totalCount: nemStats.succeeded + nemStats.failed,
            uniqueTypes: $stats.uniqueNemesisCount,
        };

        setTimeout(() => {
            if (chartCanvas) {
                safeDestroyChart("testStatus");
                $charts.testStatus = createTestStatusChart(chartCanvas, $state.filteredData.test_runs);
            }
            if (buildChartCanvas && !$isLeafNode) {
                safeDestroyChart("build");
                $charts.build = createBuildHierarchyChart(
                    buildChartCanvas,
                    $state.filteredData.test_runs,
                    $state.currentBuildLevel,
                    filterByBuildLevel
                );
            }
            if (nemesisChartCanvas) {
                safeDestroyChart("nemesis");
                $charts.nemesis = createNemesisChart(
                    nemesisChartCanvas,
                    $state.filteredData.nemesis_data,
                    (name: string) => {
                        $state.selectedNemesis = name;
                    }
                );
            }
            if (nemesisStatsCanvas) {
                safeDestroyChart("nemesisStats");
                $charts.nemesisStats = createNemesisStatsPieChart(nemesisStatsCanvas, $stats.nemesisStats);
            }
        }, 0);
    }

    /**
     * @description Creates a pie chart showing test status distribution
     * @param {HTMLCanvasElement} canvas - Canvas element to render chart
     * @param {TestRun[]} testRuns - Array of test run data
     * @returns {ChartType} Chart.js instance
     */
    function createTestStatusChart(canvas: HTMLCanvasElement, testRuns: TestRun[]): ChartType {
        const statusCounts = testRuns.reduce((acc, run) => {
            acc[run.status] = (acc[run.status] || 0) + 1;
            return acc;
        }, {} as Record<string, number>);
        const simplifiedCounts = {
            succeeded: statusCounts.passed || 0,
            failed: (statusCounts.failed || 0) + (statusCounts.error || 0) + (statusCounts.test_error || 0),
        };

        return new Chart(canvas, {
            type: "pie",
            data: {
                labels: ["Succeeded", "Failed"],
                datasets: [
                    {
                        data: [simplifiedCounts.succeeded, simplifiedCounts.failed],
                        backgroundColor: ["#4bc0c0", "#ff6384"],
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "top", labels: { font: { size: 11 } } },
                    title: { display: true, text: "Test Status Distribution" },
                },
            },
        }) as ChartType;
    }

    /**
     * @description Creates a stacked bar chart showing build hierarchy stats
     * @param {HTMLCanvasElement} canvas - Canvas element to render chart
     * @param {TestRun[]} testRuns - Array of test run data
     * @param {string} currentBuildLevel - Current build level filter
     * @param {(buildPrefix: string) => void} onClick - Callback for bar click
     * @returns {ChartType} Chart.js instance
     */
    function createBuildHierarchyChart(
        canvas: HTMLCanvasElement,
        testRuns: TestRun[],
        currentBuildLevel: string,
        onClick: (buildPrefix: string) => void
    ): ChartType {
        const buildLevels = getBuildLevels(testRuns, currentBuildLevel);
        const displayLabels = currentBuildLevel
            ? buildLevels.map((l) => l.replace(currentBuildLevel + "/", ""))
            : buildLevels;
        const statusCounts = buildLevels.map((level) => {
            const runs = testRuns.filter((r) => r.build_id.startsWith(level));
            return {
                succeeded: runs.filter((r) => r.status === "passed").length,
                failed: runs.filter((r) => ["failed", "error", "test_error"].includes(r.status)).length,
            };
        });

        return new Chart(canvas, {
            type: "bar",
            data: {
                labels: displayLabels,
                datasets: [
                    { label: "Succeeded", data: statusCounts.map((c) => c.succeeded), backgroundColor: "#28a745" },
                    { label: "Failed", data: statusCounts.map((c) => c.failed), backgroundColor: "#dc3545" },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: true, axis: "x" },
                onHover: (event, chartElements) => {
                    (event.native?.target as HTMLCanvasElement).style.cursor =
                        chartElements.length > 0 ? "pointer" : "default";
                },
                scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
                plugins: { title: { display: true, text: "Build Hierarchy Stats" }, legend: { position: "bottom" } },
                onClick: (event, elements) => {
                    if (elements.length) {
                        const clickBuildLevel = buildLevels[elements[0].index];
                        if (currentBuildLevel !== clickBuildLevel) onClick(clickBuildLevel);
                    }
                },
            },
        }) as ChartType;
    }

    /**
     * @description Creates a stacked bar chart showing nemesis success/failure counts
     * @param {HTMLCanvasElement} canvas - Canvas element to render chart
     * @param {NemesisData[]} nemesisData - Array of nemesis data
     * @param {(name: string) => void} onClick - Callback for bar click
     * @returns {ChartType} Chart.js instance
     */
    function createNemesisChart(
        canvas: HTMLCanvasElement,
        nemesisData: NemesisData[],
        onClick: (name: string) => void
    ): ChartType {
        const nemesisNames = [...new Set(nemesisData.map((n) => n.name))].sort();
        const successCounts = nemesisNames.map(
            (name) => nemesisData.filter((n) => n.name === name && n.status === "succeeded").length
        );
        const failureCounts = nemesisNames.map(
            (name) => nemesisData.filter((n) => n.name === name && n.status === "failed").length
        );

        return new Chart(canvas, {
            type: "bar",
            data: {
                labels: nemesisNames,
                datasets: [
                    { label: "Succeeded", data: successCounts, backgroundColor: "#4bc0c0" },
                    { label: "Failed", data: failureCounts, backgroundColor: "#ff6384" },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: true, axis: "x" },
                onHover: (event, chartElements) => {
                    (event.native?.target as HTMLCanvasElement).style.cursor =
                        chartElements.length > 0 ? "pointer" : "default";
                },
                scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } },
                plugins: {
                    title: { display: true, text: "Nemesis Success and Failure Counts" },
                    legend: { position: "bottom" },
                    tooltip: {
                        mode: "index",
                        intersect: false,
                        position: "nearest",
                        callbacks: {
                            title: (tooltipItems) => {
                                return tooltipItems[0].label;
                            },
                            label: (context) => {
                                const label = context.dataset.label;
                                const value = context.parsed.y;
                                return `${label}: ${value}`;
                            },
                        },
                    },
                },
                onClick: (event, elements) => {
                    if (elements.length) onClick(nemesisNames[elements[0].index]);
                },

            },
        }) as ChartType;
    }

    /**
     * @description Creates a pie chart showing nemesis status distribution
     * @param {HTMLCanvasElement} canvas - Canvas element to render chart
     * @param {typeof $stats.nemesisStats} nemesisStats - Nemesis statistics object
     * @returns {ChartType} Chart.js instance
     */
    function createNemesisStatsPieChart(
        canvas: HTMLCanvasElement,
        nemesisStats: typeof $stats.nemesisStats
    ): ChartType {
        return new Chart(canvas, {
            type: "pie",
            data: {
                labels: ["Succeeded", "Failed"],
                datasets: [
                    { data: [nemesisStats.succeeded, nemesisStats.failed], backgroundColor: ["#4bc0c0", "#ff6384"] },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "top", labels: { font: { size: 11 } } },
                    title: { display: true, text: "Nemesis Status Distribution" },
                },
            },
        }) as ChartType;
    }

    /**
     * @description Extracts unique build levels from test run data
     * @param {TestRun[]} data - Array of test run data
     * @param {string} currentBuildLevel - Current build level filter
     * @returns {string[]} Array of build level strings
     */
    function getBuildLevels(data: TestRun[], currentBuildLevel: string): string[] {
        const prefixLength = currentBuildLevel ? currentBuildLevel.split("/").length : 0;
        return [
            ...new Set(
                data.map((run) =>
                    run.build_id
                        .split("/")
                        .slice(0, prefixLength + 1)
                        .join("/")
                )
            ),
        ].sort();
    }

    /**
     * @description Zooms out one level in the build hierarchy
     */
    function zoomOut() {
        if (!$state.currentBuildLevel) return;
        const parts = $state.currentBuildLevel.split("/");
        parts.pop();
        filterByBuildLevel(parts.join("/"));
    }

    onMount(() => {
        $state.collapsed = true;
    });
</script>

<div class="accordion">
    <div class="accordion-item">
        <h2 class="accordion-header">
            <button
                class="accordion-button collapsed"
                aria-expanded={!$state.collapsed}
                on:click={() => {
                    $state.collapsed = !$state.collapsed;
                    if (!$state.collapsed && !$state.allData.test_runs.length) fetchData();
                }}
            >
                Graphed Statistics
            </button>
        </h2>
        <div class="accordion-collapse collapse" class:show={!$state.collapsed}>
            <div class="accordion-body">
                {#if $state.errorMsg}
                    <div class="alert alert-danger">
                        {$state.errorMsg}
                        <button class="btn btn-sm btn-outline-primary ms-2" on:click={fetchData}>Retry</button>
                    </div>
                {:else if $state.loading}
                    <div class="text-center my-3">
                        <div class="spinner-border" role="status" />
                        <span class="ms-2">Loading...</span>
                    </div>
                {:else}
                    <Filters
                        allData={$state.allData}
                        selectedFilter={$state.selectedFilter}
                        onFilterChange={(filter) => {
                            applyFilter(filter);
                            if (filter === "") {
                                $state.currentBuildLevel = "";
                                $state.selectedNemesis = null;
                            }
                        }}
                    />

                    <div class="row">
                        <div class="col-md-4">
                            <div class="chart-container"><canvas bind:this={chartCanvas} height="400" /></div>
                            <div class="alert alert-info text-center py-2 mb-2">
                                Total Duration: {($stats.totalDuration / 3600).toFixed(2)} hours
                            </div>
                            <div class="alert alert-secondary text-center py-2 mb-2">
                                Unique Tests: {$stats.uniqueTests}
                            </div>
                            <h5 class="mt-4 mb-3">Nemesis Statistics</h5>
                            <div class="chart-container"><canvas bind:this={nemesisStatsCanvas} height="300" /></div>
                            <div class="alert alert-secondary text-center py-2 mb-2">
                                Unique Nemesis Types: {$stats.uniqueNemesisCount}
                            </div>
                            <div class="alert alert-secondary text-center py-2 mb-2">
                                Nemesis Duration: {($stats.nemesisStats.totalDuration / 3600).toFixed(2)} hours
                            </div>
                        </div>
                        <div class="col-md-8">
                            {#if $state.currentBuildLevel}
                                <div class="mb-3">
                                    <button class="btn btn-sm btn-outline-primary" on:click={zoomOut}
                                        >Zoom Out (Current: {$state.currentBuildLevel})</button
                                    >
                                </div>
                            {/if}
                            {#if $isLeafNode}
                                <div>
                                    <TestRunTable
                                        testRuns={$state.filteredData.test_runs}
                                        onClose={zoomOut}
                                    />
                                </div>
                            {:else}
                                <div class="chart-container"><canvas bind:this={buildChartCanvas} height="400" /></div>
                            {/if}
                            <div class="chart-container"><canvas bind:this={nemesisChartCanvas} height="400" /></div>
                        </div>
                    </div>

                    {#if $state.selectedNemesis}
                        <div class="row">
                            <div class="col-12">
                                <NemesisTable
                                    nemesisName={$state.selectedNemesis}
                                    nemesisData={$state.filteredData.nemesis_data}
                                    onClose={() => ($state.selectedNemesis = null)}
                                />
                            </div>
                        </div>
                    {/if}
                {/if}
            </div>
        </div>
    </div>
</div>

<style>
    .chart-container {
        width: 100%;
        height: 450px;
        margin-bottom: 3rem;
        padding: 1rem;
    }
    .accordion-body {
        padding: 2rem;
    }
    .bi {
        position: absolute;
        right: 0.5rem;
        top: 50%;
        transform: translateY(-50%);
    }
    @media (max-width: 768px) {
        .chart-container {
            height: 300px;
        }
    }
</style>
