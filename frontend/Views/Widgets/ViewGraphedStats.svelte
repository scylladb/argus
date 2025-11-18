<script lang="ts">
    import { onMount } from "svelte";
    import Chart from "chart.js/auto";
    import type { Chart as ChartType } from "chart.js/auto";
    import type { TestRun, NemesisData, DataResponse } from "./ViewGraphedStats/Interfaces";
    import NemesisTable from "./ViewGraphedStats/NemesisTable.svelte";
    import TestRunTable from "./ViewGraphedStats/TestRunTable.svelte";
    import Filters from "./ViewGraphedStats/Filters.svelte";

    interface Props {
        dashboardObject: { id: string };
        settings: {testFilters: string[]};
    }

    interface WidgetState {
        loading: boolean;
        errorMsg: string;
        collapsed: boolean;
        allData: DataResponse;
        filteredData: DataResponse;
        currentBuildLevel: string;
        selectedNemesis: string | null;
        selectedFilter: string;
    }

    let {
        dashboardObject,
        settings,
    }: Props = $props();

    const widgetState: WidgetState = $state({
        loading: true,
        errorMsg: "",
        collapsed: true,
        allData: { test_runs: [], nemesis_data: [] },
        filteredData: { test_runs: [], nemesis_data: [] },
        currentBuildLevel: "",
        selectedNemesis: null,
        selectedFilter: "",
    });

    const charts: Record<string, ChartType> = $state({});

    const stats = $state({
        totalDuration: 0,
        uniqueTests: 0,
        uniqueNemesisCount: 0,
        nemesisStats: { totalCount: 0, succeeded: 0, failed: 0, totalDuration: 0, uniqueTypes: 0 },
    });

    const isLeafNode = () => {
        if (!widgetState.currentBuildLevel) return false;
        return !widgetState.allData.test_runs.some(
            (run) =>
                run.build_id.startsWith(widgetState.currentBuildLevel + "/") && run.build_id !== widgetState.currentBuildLevel
        );
    };

    let chartCanvas: HTMLCanvasElement | null = $state(null);
    let buildChartCanvas: HTMLCanvasElement | null = $state(null);
    let nemesisChartCanvas: HTMLCanvasElement | null = $state(null);
    let nemesisStatsCanvas: HTMLCanvasElement | null = $state(null);

    /**
     * @description Fetches data from the API and updates state
     * @async
     */
    async function fetchData() {
        widgetState.loading = true;
        widgetState.errorMsg = "";
        try {
            // Prepare filters if they exist
            const filters = settings.testFilters && settings.testFilters.length > 0
                ? `&filters=${encodeURIComponent(JSON.stringify(settings.testFilters))}`
                : '';

            const response = await fetch(`/api/v1/views/widgets/graphed_stats?view_id=${dashboardObject.id}${filters}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            if (data.status === "error") throw new Error(data.response.exception);

            widgetState.allData = data.response || { test_runs: [], nemesis_data: [] };
            applyFilter(widgetState.selectedFilter);
        } catch (error) {
            widgetState.errorMsg = `Failed to load graphed stats: ${(error as Error).message}`;
        } finally {
            widgetState.loading = false;
        }
    }

    /**
     * @description Applies version filter to data
     * @param {string} filter - Version filter string
     */
    function applyFilter(filter: string) {
        widgetState.selectedFilter = filter;
        widgetState.filteredData = {
            test_runs: widgetState.allData.test_runs.filter((run) => (filter ? run.version.startsWith(filter) : true)),
            nemesis_data: widgetState.allData.nemesis_data.filter((n) => (filter ? n.version.startsWith(filter) : true)),
        };
        widgetState.currentBuildLevel = "";
        widgetState.selectedNemesis = null;
        updateStatsAndCharts();
    }

    /**
     * @description Filters data by build level hierarchy
     * @param {string} buildPrefix - Build level prefix to filter by
     */
    function filterByBuildLevel(buildPrefix: string) {
        widgetState.currentBuildLevel = buildPrefix;
        const hasChildren = widgetState.allData.test_runs.some(
            (run) => run.build_id.startsWith(buildPrefix + "/") && run.build_id !== buildPrefix
        );

        widgetState.filteredData = {
            test_runs: widgetState.allData.test_runs.filter(
                (run) =>
                    (widgetState.selectedFilter ? run.version.startsWith(widgetState.selectedFilter) : true) &&
                    (buildPrefix
                        ? hasChildren
                            ? run.build_id.startsWith(buildPrefix)
                            : run.build_id === buildPrefix
                        : true)
            ),
            nemesis_data: widgetState.allData.nemesis_data.filter(
                (n) =>
                    (widgetState.selectedFilter ? n.version.startsWith(widgetState.selectedFilter) : true) &&
                    (buildPrefix
                        ? hasChildren
                            ? n.build_id.startsWith(buildPrefix)
                            : n.build_id === buildPrefix
                        : true)
            ),
        };

        if (widgetState.filteredData.test_runs.length === 0 && !hasChildren) {
            widgetState.filteredData = {
                test_runs: widgetState.allData.test_runs.filter(
                    (run) =>
                        (widgetState.selectedFilter ? run.version.startsWith(widgetState.selectedFilter) : true) &&
                        (buildPrefix ? run.build_id.startsWith(buildPrefix) : true)
                ),
                nemesis_data: widgetState.allData.nemesis_data.filter(
                    (n) =>
                        (widgetState.selectedFilter ? n.version.startsWith(widgetState.selectedFilter) : true) &&
                        (buildPrefix ? n.build_id.startsWith(buildPrefix) : true)
                ),
            };
        }

        widgetState.selectedNemesis = null;
        updateStatsAndCharts();
    }

    /**
     * @description Updates statistics and recreates charts
     */
    function updateStatsAndCharts() {
        stats.totalDuration = widgetState.filteredData.test_runs.reduce((sum, run) => sum + Math.max(0, run.duration), 0);
        stats.uniqueTests = new Set(widgetState.filteredData.test_runs.map((run) => run.build_id)).size;
        stats.uniqueNemesisCount = new Set(widgetState.filteredData.nemesis_data.map((n) => n.name)).size;

        const nemStats = widgetState.filteredData.nemesis_data.reduce(
            (acc, n) => {
                acc.totalDuration += Math.max(0, n.duration);
                acc[n.status === "succeeded" ? "succeeded" : "failed"]++;
                return acc;
            },
            { succeeded: 0, failed: 0, totalDuration: 0 }
        );

        stats.nemesisStats = {
            ...nemStats,
            totalCount: nemStats.succeeded + nemStats.failed,
            uniqueTypes: stats.uniqueNemesisCount,
        };

        setTimeout(() => {
            if (chartCanvas) {
                charts["testStatus"]?.destroy();
                charts.testStatus = createTestStatusChart(chartCanvas, widgetState.filteredData.test_runs);
            }
            if (buildChartCanvas && !isLeafNode()) {
                charts["build"]?.destroy();
                charts.build = createBuildHierarchyChart(
                    buildChartCanvas,
                    widgetState.filteredData.test_runs,
                    widgetState.currentBuildLevel,
                    filterByBuildLevel
                );
            }
            if (nemesisChartCanvas) {
                charts["nemesis"]?.destroy();
                charts.nemesis = createNemesisChart(
                    nemesisChartCanvas,
                    widgetState.filteredData.nemesis_data,
                    (name: string) => {
                        widgetState.selectedNemesis = name;
                    }
                );
            }
            if (nemesisStatsCanvas) {
                charts["nemesisStats"]?.destroy();
                charts.nemesisStats = createNemesisStatsPieChart(nemesisStatsCanvas, stats.nemesisStats);
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
                    event.native.target.style.cursor = chartElements.length > 0 ? "pointer" : "default";
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
                    event.native.target.style.cursor = chartElements.length > 0 ? "pointer" : "default";
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
     * @param {typeof stats.nemesisStats} nemesisStats - Nemesis statistics object
     * @returns {ChartType} Chart.js instance
     */
    function createNemesisStatsPieChart(
        canvas: HTMLCanvasElement,
        nemesisStats: typeof stats.nemesisStats
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
        if (!widgetState.currentBuildLevel) return;
        const parts = widgetState.currentBuildLevel.split("/");
        parts.pop();
        filterByBuildLevel(parts.join("/"));
    }

    onMount(() => {
        widgetState.collapsed = true;
    });
</script>

<div class="accordion">
    <div class="accordion-item">
        <h2 class="accordion-header">
            <button
                class="accordion-button collapsed"
                aria-expanded={!widgetState.collapsed}
                onclick={() => {
                    widgetState.collapsed = !widgetState.collapsed;
                    if (!widgetState.collapsed && !widgetState.allData.test_runs.length) fetchData();
                }}
            >
                Graphed Statistics
            </button>
        </h2>
        <div class="accordion-collapse collapse" class:show={!widgetState.collapsed}>
            <div class="accordion-body">
                {#if widgetState.errorMsg}
                    <div class="alert alert-danger">
                        {widgetState.errorMsg}
                        <button class="btn btn-sm btn-outline-primary ms-2" onclick={fetchData}>Retry</button>
                    </div>
                {:else if widgetState.loading}
                    <div class="text-center my-3">
                        <div class="spinner-border" role="status"></div>
                        <span class="ms-2">Loading...</span>
                    </div>
                {:else}
                    <Filters
                        allData={widgetState.allData}
                        selectedFilter={widgetState.selectedFilter}
                        onFilterChange={(filter) => {
                            applyFilter(filter);
                            if (filter === "") {
                                widgetState.currentBuildLevel = "";
                                widgetState.selectedNemesis = null;
                            }
                        }}
                    />

                    <div class="row">
                        <div class="col-md-4">
                            <div class="chart-container"><canvas bind:this={chartCanvas} height="400"></canvas></div>
                            <div class="alert alert-info text-center py-2 mb-2">
                                Total Duration: {(stats.totalDuration / 3600).toFixed(2)} hours
                            </div>
                            <div class="alert alert-secondary text-center py-2 mb-2">
                                Unique Tests: {stats.uniqueTests}
                            </div>
                            <h5 class="mt-4 mb-3">Nemesis Statistics</h5>
                            <div class="chart-container"><canvas bind:this={nemesisStatsCanvas} height="300"></canvas></div>
                            <div class="alert alert-secondary text-center py-2 mb-2">
                                Unique Nemesis Types: {stats.uniqueNemesisCount}
                            </div>
                            <div class="alert alert-secondary text-center py-2 mb-2">
                                Nemesis Duration: {(stats.nemesisStats.totalDuration / 3600).toFixed(2)} hours
                            </div>
                        </div>
                        <div class="col-md-8">
                            {#if widgetState.currentBuildLevel}
                                <div class="mb-3">
                                    <button class="btn btn-sm btn-outline-primary" onclick={zoomOut}
                                        >Zoom Out (Current: {widgetState.currentBuildLevel})</button
                                    >
                                </div>
                            {/if}
                            {#if isLeafNode()}
                                <div>
                                    <TestRunTable
                                        testRuns={widgetState.filteredData.test_runs}
                                        onClose={zoomOut}
                                    />
                                </div>
                            {:else}
                                <div class="chart-container"><canvas bind:this={buildChartCanvas} height="400"></canvas></div>
                            {/if}
                            <div class="chart-container"><canvas bind:this={nemesisChartCanvas} height="400"></canvas></div>
                        </div>
                    </div>

                    {#if widgetState.selectedNemesis}
                        <div class="row">
                            <div class="col-12">
                                <NemesisTable
                                    nemesisName={widgetState.selectedNemesis}
                                    nemesisData={widgetState.filteredData.nemesis_data}
                                    onClose={() => (widgetState.selectedNemesis = null)}
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
