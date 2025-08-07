<script lang="ts">
    import { run as run_1 } from 'svelte/legacy';

    import { onMount } from "svelte";
    import Chart from "chart.js/auto";

    let { viewId, dashboardObject } = $props();
    let chartCanvas = $state();
    let chart;
    let barChartCanvas = $state();
    let barChart;
    let versions = $state([]);
    let releases = $state([]);
    let selectedFilter = $state("");
    let totalDuration = $state(0);
    let uniqueNemesisCount = $state(0);
    let allNemesisData = [];
    let errorMsg = $state("");
    let loading = $state(true);
    let filteredData = $state([]);
    let collapsed = true;
    let selectedNemesis = $state(null);

    // Pagination state
    let itemsPerPage = 20;
    let currentPage = $state(1);

    // Sorting state
    let sortField = $state("status");
    let sortDirection = $state("asc"); // "asc" or "desc"

    let paginatedRuns = $state([]);


    async function fetchData() {
        try {
            const response = await fetch(`/api/v1/views/widgets/nemesis_data?view_id=${dashboardObject.id}`);

            if (!response.ok) {
                const error = await response.text();
                throw new Error(`HTTP error! status: ${response.status} ${response.statusText} - ${error}`);
            }

            const data = await response.json();

            if (data.status === "error") {
                throw new Error(
                    `Failed to fetch nemesis data: ${data.response.exception} - ${data.response.arguments.join(
                        ", "
                    )} - Trace ID: ${data.response.trace_id}`
                );
            }

            allNemesisData = data.response.nemesis_data || [];
            loading = false;
            return allNemesisData;
        } catch (error) {
            console.error("Failed to fetch nemesis data:", error);
            errorMsg = `Failed to load Nemesis data: ${error}`;
            loading = false;
            return [];
        }
    }

    function extractVersionsAndReleases(data) {
        versions = [...new Set(data.map((nemesis) => nemesis.version))].sort();
        releases = [...new Set(versions.map((version) => version.split(".").slice(0, 2).join(".")))].sort();
    }

    function filterData(data) {
        return selectedFilter ? data.filter((nemesis) => nemesis.version.startsWith(selectedFilter)) : data;
    }

    function calculateTotalDuration(data) {
        return data.reduce((total, nemesis) => total + nemesis.duration, 0);
    }

    function calculateUniqueNemesisCount(data) {
        return new Set(data.map((nemesis) => nemesis.name)).size;
    }

    function calculateStatusCounts(data) {
        return data.reduce(
            (counts, nemesis) => {
                if (nemesis.status === "succeeded") {
                    counts.succeeded++;
                } else if (nemesis.status === "failed") {
                    counts.failed++;
                }
                return counts;
            },
            { succeeded: 0, failed: 0 }
        );
    }

    function calculateNemesisTypeStats(data) {
        const nemesisNames = [...new Set(data.map((nemesis) => nemesis.name))].sort();
        return {
            names: nemesisNames,
            successCounts: nemesisNames.map(
                (name) => data.filter((nemesis) => nemesis.name === name && nemesis.status === "succeeded").length
            ),
            failureCounts: nemesisNames.map(
                (name) => data.filter((nemesis) => nemesis.name === name && nemesis.status === "failed").length
            ),
        };
    }

    function updateCharts(data) {
        const statusCounts = calculateStatusCounts(data);
        createPieChart(statusCounts);
        const typeStats = calculateNemesisTypeStats(data);
        createBarChart(typeStats);

        totalDuration = calculateTotalDuration(data);
        uniqueNemesisCount = calculateUniqueNemesisCount(data);
    }

    function createPieChart(statusCounts) {
        if (chart) {
            chart.destroy();
        }
        chart = new Chart(chartCanvas, {
            type: "pie",
            data: {
                labels: ["Succeeded", "Failed"],
                datasets: [
                    {
                        data: [statusCounts.succeeded, statusCounts.failed],
                        backgroundColor: ["rgb(75, 192, 192)", "rgb(255, 99, 132)"],
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "top",
                        labels: {
                            generateLabels: (chart) => {
                                const data = chart.data;
                                if (data.labels.length && data.datasets.length) {
                                    return data.labels.map((label, i) => {
                                        const value = data.datasets[0].data[i];
                                        return {
                                            text: `${label}: ${value}`,
                                            fillStyle: data.datasets[0].backgroundColor[i],
                                            hidden:
                                                isNaN(data.datasets[0].data[i]) ||
                                                chart.getDatasetMeta(0).data[i].hidden,
                                            index: i,
                                        };
                                    });
                                }
                                return [];
                            },
                            font: {
                                size: 11,
                            },
                        },
                    },
                    title: {
                        display: true,
                        text: "Nemesis Status Distribution",
                    },
                },
            },
        });
    }

    function createBarChart(typeStats) {
        if (barChart) {
            barChart.destroy();
        }

        barChart = new Chart(barChartCanvas, {
            type: "bar",
            data: {
                labels: typeStats.names,
                datasets: [
                    {
                        label: "Succeeded",
                        data: typeStats.successCounts,
                        backgroundColor: "rgb(75, 192, 192)",
                    },
                    {
                        label: "Failed",
                        data: typeStats.failureCounts,
                        backgroundColor: "rgb(255, 99, 132)",
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false,
                    },
                    title: {
                        display: true,
                        text: "Nemesis Success and Failure Counts",
                    },
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
                interaction: {
                    mode: "index",
                    intersect: true,
                    axis: "x",
                },
                onHover: (event, chartElements) => {
                    // Only change cursor when hovering over a bar
                    const canvas = event.native.target;
                    canvas.style.cursor = chartElements.length > 0 ? "pointer" : "default";
                },
                scales: {
                    x: {
                        stacked: true,
                    },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                    },
                },
                onClick: (event, elements) => {
                    if (elements.length > 0) {
                        const index = elements[0].index;
                        const nemesisName = typeStats.names[index];
                        handleNemesisClick(nemesisName);
                    }
                },
            },
        });
    }

    function handleNemesisClick(nemesisName) {
        selectedNemesis = nemesisName;
        // Reset pagination and sorting when selecting a new nemesis
        currentPage = 1;
        sortField = "status";
        sortDirection = "asc";
    }

    function clearSelectedNemesis() {
        selectedNemesis = null;
    }

    // Sort runs based on the current sort field and direction
    function sortRuns(runs) {
        return [...runs].sort((a, b) => {
            let comparison = 0;

            // Default sorting (status first, then by run_id)
            if (sortField === "status") {
                // Status sorting (failed first by default)
                if (a.status === "failed" && b.status !== "failed") comparison = -1;
                else if (a.status !== "failed" && b.status === "failed") comparison = 1;
                else comparison = b.run_id.localeCompare(a.run_id); // Most recent first
            } else if (sortField === "run_id") {
                comparison = a.run_id.localeCompare(b.run_id);
            } else if (sortField === "duration") {
                comparison = a.duration - b.duration;
            } else if (sortField === "version") {
                comparison = a.version.localeCompare(b.version);
            } else if (sortField === "start_time") {
                // Use numeric comparison for timestamps
                comparison = a.start_time - b.start_time;
            }

            // Apply sort direction
            return sortDirection === "asc" ? comparison : -comparison;
        });
    }

    // Toggle sorting when a column header is clicked
    function toggleSort(field) {
        // If clicking the same field, toggle direction
        if (sortField === field) {
            sortDirection = sortDirection === "asc" ? "desc" : "asc";
        } else {
            // Clear previous sort field and set new one
            sortField = field;
            sortDirection = "asc";
        }

        // Force a reactive update by creating a new array
        if (selectedNemesis) {
            const runs = filteredData.filter((nemesis) => nemesis.name === selectedNemesis);
            const sortedRuns = sortRuns(runs);
            const startIndex = (currentPage - 1) * itemsPerPage;
            paginatedRuns = [...sortedRuns.slice(startIndex, startIndex + itemsPerPage)];
        }
    }

    // Get total number of pages
    function getTotalPages(nemesisName) {
        if (!nemesisName) return 0;
        const runs = filteredData.filter((nemesis) => nemesis.name === nemesisName);
        return Math.ceil(runs.length / itemsPerPage);
    }

    function changePage(page) {
        currentPage = page;
    }

    // Extract the first 3 lines of a stack trace
    function getStackTracePreview(stackTrace) {
        if (!stackTrace) return "";

        const lines = stackTrace.split("\n");
        return lines.slice(0, 3).join("\n");
    }

    // Check if stack trace has more than 3 lines
    function hasMoreStackTraceLines(stackTrace) {
        if (!stackTrace) return false;

        return stackTrace.split("\n").length > 3;
    }

    function formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const remainingSeconds = Math.floor(seconds % 60);

        return `${hours}h ${minutes}m ${remainingSeconds}s`;
    }

    function formatTimestamp(timestamp) {
        if (!timestamp) return "N/A";
        // Convert Unix timestamp to Date object
        const date = new Date(timestamp * 1000);
        return date.toLocaleDateString("en-CA", { timeZone: "UTC" });
    }

    function applyFilter(filter) {
        selectedFilter = filter;
        filteredData = filterData(allNemesisData);
        updateCharts(filteredData);
        selectedNemesis = null;
    }

    function toggleCollapsed() {
        collapsed = !collapsed;
        if (!collapsed && !allNemesisData.length) {
            fetchData().then((data) => {
                if (!errorMsg) {
                    extractVersionsAndReleases(data);
                    filteredData = filterData(data);
                    updateCharts(filteredData);
                }
            });
        }
    }

    function toggleStackTrace(runId) {
        const preview = document.getElementById(`preview-${runId}`);
        const full = document.getElementById(`full-${runId}`);
        const button = document.getElementById(`btn-${runId}`);

        if (!preview || !full || !button) {
            console.error(`Could not find elements for run ID: ${runId}`);
            return;
        }

        if (full.style.display === "block") {
            // Currently showing full, switch to preview
            preview.style.display = "block";
            full.style.display = "none";
            button.textContent = "Show More";
        } else {
            // Currently showing preview, switch to full
            preview.style.display = "none";
            full.style.display = "block";
            button.textContent = "Show Less";
        }
    }

    onMount(() => {
        collapsed = true;
    });
    // Watch for changes in selectedNemesis, currentPage, sortField, and sortDirection
    run_1(() => {
        if (selectedNemesis) {
            const runs = filteredData.filter((nemesis) => nemesis.name === selectedNemesis);
            const sortedRuns = sortRuns(runs);
            const startIndex = (currentPage - 1) * itemsPerPage;
            paginatedRuns = sortedRuns.slice(startIndex, startIndex + itemsPerPage);
        } else {
            paginatedRuns = [];
        }
    });
</script>

<div class="accordion" id="nemesisStatsAccordion">
    <div class="accordion-item">
        <h2 class="accordion-header" id="headingNemesisStats">
            <button
                class="accordion-button collapsed"
                type="button"
                data-bs-toggle="collapse"
                data-bs-target="#nemesisStats"
                aria-expanded="false"
                aria-controls="nemesisStats"
                onclick={toggleCollapsed}
            >
                Nemesis Statistics
            </button>
        </h2>
        <div
            id="nemesisStats"
            class="accordion-collapse collapse"
            aria-labelledby="headingNemesisStats"
            data-bs-parent="#nemesisStatsAccordion"
        >
            <div class="accordion-body">
                {#if errorMsg}
                    <div class="alert alert-danger" role="alert">
                        {errorMsg}
                    </div>
                {:else if !loading}
                    <div class="btn-group mb-3" role="group">
                        <button
                            class:active={selectedFilter === ""}
                            class="btn btn-outline-secondary"
                            onclick={() => applyFilter("")}>All</button
                        >
                        {#each releases as release}
                            <button
                                class:active={selectedFilter === release}
                                class="btn btn-outline-secondary"
                                onclick={() => applyFilter(release)}>{release}</button
                            >
                        {/each}
                    </div>
                    <div class="btn-group mb-3" role="group">
                        {#each versions as version}
                            <button
                                class:active={selectedFilter === version}
                                class="btn btn-outline-primary btn-sm"
                                onclick={() => applyFilter(version)}>{version}</button
                            >
                        {/each}
                    </div>

                    <div class="row">
                        <div class="col-md-3">
                            <div class="small-chart-container mb-3">
                                <canvas bind:this={chartCanvas}></canvas>
                            </div>
                            <div class="alert alert-info text-center py-2">
                                <small>Total Duration: {(totalDuration / 3600).toFixed(2)} hours</small>
                            </div>
                            <div class="alert alert-secondary text-center py-2 my-2">
                                <small>Unique Nemesis Types: {uniqueNemesisCount}</small>
                            </div>
                        </div>
                        <div class="col-md-9">
                            <div class="bar-chart-container">
                                <canvas bind:this={barChartCanvas}></canvas>
                            </div>
                        </div>
                    </div>

                    {#if selectedNemesis}
                        <div class="nemesis-details mt-4">
                            <div class="d-flex justify-content-between align-items-center mb-3">
                                <h5>Nemesis: {selectedNemesis}</h5>
                                <button class="btn btn-sm btn-outline-secondary" onclick={clearSelectedNemesis}>
                                    <i class="bi bi-x"></i> Close
                                </button>
                            </div>

                            <div class="table-responsive">
                                {#key paginatedRuns}
                                    <table class="table table-striped table-hover">
                                        <thead>
                                            <tr>
                                                <th
                                                    class="status-column sortable"
                                                    onclick={() => toggleSort("status")}
                                                >
                                                    Status
                                                    <span class="sort-indicator">
                                                        {#if sortField === "status"}
                                                            {#if sortDirection === "desc"}
                                                                <i class="fas fa-sort-down"></i>
                                                            {:else}
                                                                <i class="fas fa-sort-up"></i>
                                                            {/if}
                                                        {/if}
                                                    </span>
                                                </th>
                                                <th
                                                    class="start-time-column sortable"
                                                    onclick={() => toggleSort("start_time")}
                                                >
                                                    Start Time
                                                    <span class="sort-indicator">
                                                        {#if sortField === "start_time"}
                                                            {#if sortDirection === "desc"}
                                                                <i class="fas fa-sort-down"></i>
                                                            {:else}
                                                                <i class="fas fa-sort-up"></i>
                                                            {/if}
                                                        {/if}
                                                    </span>
                                                </th>
                                                <th
                                                    class="duration-column sortable"
                                                    onclick={() => toggleSort("duration")}
                                                >
                                                    Duration
                                                    <span class="sort-indicator">
                                                        {#if sortField === "duration"}
                                                            {#if sortDirection === "desc"}
                                                                <i class="fas fa-sort-down"></i>
                                                            {:else}
                                                                <i class="fas fa-sort-up"></i>
                                                            {/if}
                                                        {/if}
                                                    </span>
                                                </th>
                                                <th
                                                    class="version-column sortable"
                                                    onclick={() => toggleSort("version")}
                                                >
                                                    Version
                                                    <span class="sort-indicator">
                                                        {#if sortField === "version"}
                                                            {#if sortDirection === "desc"}
                                                                <i class="fas fa-sort-down"></i>
                                                            {:else}
                                                                <i class="fas fa-sort-up"></i>
                                                            {/if}
                                                        {/if}
                                                    </span>
                                                </th>
                                                <th>Stack Trace</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {#each paginatedRuns as run, index (run.run_id)}
                                                <tr>
                                                    <td class="status-column">
                                                        {#if run.status === "failed"}
                                                            <span class="badge bg-danger">Failed</span>
                                                        {:else}
                                                            <span class="badge bg-success">Passed</span>
                                                        {/if}
                                                    </td>
                                                    <td class="run-id-column">
                                                        <a
                                                            href={`/tests/scylla-cluster-tests/${run.run_id}`}
                                                            target="_blank"
                                                        >
                                                            {formatTimestamp(run.start_time)}
                                                        </a>
                                                    </td>
                                                    <td class="duration-column">{formatDuration(run.duration)}</td>
                                                    <td class="version-column">{run.version}</td>
                                                    <td class="stack-trace-column">
                                                        {#if run.stack_trace}
                                                            <div class="stack-trace-container">
                                                                <pre
                                                                    class="stack-trace-preview"
                                                                    id={`preview-${run.run_id}`}>{getStackTracePreview(
                                                                        run.stack_trace
                                                                    )}</pre>
                                                                <pre
                                                                    class="stack-trace-full"
                                                                    id={`full-${run.run_id}`}
                                                                    style="display: none;">{run.stack_trace}</pre>
                                                                {#if hasMoreStackTraceLines(run.stack_trace)}
                                                                    <button
                                                                        id={`btn-${run.run_id}`}
                                                                        class="btn btn-sm btn-outline-secondary mt-1"
                                                                        onclick={() => toggleStackTrace(run.run_id)}
                                                                    >
                                                                        Show More
                                                                    </button>
                                                                {/if}
                                                            </div>
                                                        {:else}
                                                            <span class="text-muted">No stack trace available</span>
                                                        {/if}
                                                    </td>
                                                </tr>
                                            {/each}
                                        </tbody>
                                    </table>
                                {/key}

                                {#if getTotalPages(selectedNemesis) > 1}
                                    <nav aria-label="Nemesis runs pagination">
                                        <ul class="pagination pagination-sm justify-content-center">
                                            <li class="page-item {currentPage === 1 ? 'disabled' : ''}">
                                                <button
                                                    class="page-link"
                                                    onclick={() => changePage(currentPage - 1)}
                                                    disabled={currentPage === 1}
                                                >
                                                    Previous
                                                </button>
                                            </li>

                                            {#each Array(getTotalPages(selectedNemesis)) as _, i}
                                                <li class="page-item {currentPage === i + 1 ? 'active' : ''}">
                                                    <button class="page-link" onclick={() => changePage(i + 1)}>
                                                        {i + 1}
                                                    </button>
                                                </li>
                                            {/each}

                                            <li
                                                class="page-item {currentPage === getTotalPages(selectedNemesis)
                                                    ? 'disabled'
                                                    : ''}"
                                            >
                                                <button
                                                    class="page-link"
                                                    onclick={() => changePage(currentPage + 1)}
                                                    disabled={currentPage === getTotalPages(selectedNemesis)}
                                                >
                                                    Next
                                                </button>
                                            </li>
                                        </ul>
                                    </nav>
                                {/if}
                            </div>
                        </div>
                    {/if}
                {:else}
                    <div class="text-center my-3">
                        <span>Loading nemesis stats...</span>
                    </div>
                {/if}
            </div>
        </div>
    </div>
</div>

<style>
    .bar-chart-container {
        width: 100%;
        height: 600px;
    }

    .small-chart-container {
        height: 250px;
    }

    .stack-trace-preview {
        font-size: 0.8rem;
        margin-bottom: 0;
        background-color: #f8f9fa;
        padding: 0.25rem;
        border-radius: 0.25rem;
        white-space: pre-wrap;
        word-break: break-word;
        max-height: 4.5em;
        overflow: hidden;
    }

    .stack-trace-full {
        font-size: 0.8rem;
        margin-bottom: 0;
        background-color: #f8f9fa;
        padding: 0.25rem;
        border-radius: 0.25rem;
        white-space: pre-wrap;
        word-break: break-word;
        max-height: 200px;
        overflow-y: auto;
    }

    .stack-trace-container {
        position: relative;
    }

    .nemesis-details {
        border-top: 1px solid #dee2e6;
        padding-top: 1.5rem;
    }

    .start-time-column {
        width: 120px;
    }

    .duration-column {
        width: 120px;
    }

    .version-column {
        width: 120px;
    }

    .status-column {
        width: 80px;
    }

    /* Sortable table headers */
    th {
        cursor: pointer;
        user-select: none;
    }

    th:hover {
        background-color: rgba(0, 0, 0, 0.05);
    }

    .sortable {
        position: relative;
    }

    .sort-indicator {
        position: absolute;
        right: 10px;
        top: 50%;
        transform: translateY(-50%);
        font-size: 0.8rem;
        color: #6c757d;
    }
</style>
