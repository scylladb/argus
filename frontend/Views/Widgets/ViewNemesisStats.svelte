<script>
    import { onMount } from "svelte";
    import Chart from "chart.js/auto";

    export let viewId;
    export let dashboardObject;
    let chartCanvas;
    let chart;
    let barChartCanvas;
    let barChart;
    let versions = [];
    let releases = [];
    let selectedFilter = "";
    let totalDuration = 0;
    let uniqueNemesisCount = 0;
    let allNemesisData = [];
    let errorMsg = "";
    let loading = true;
    let filteredData = [];
    let collapsed = true;

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

        // Update summary stats
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
                    intersect: false,
                    axis: "x",
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
            },
        });
    }

    function applyFilter(filter) {
        selectedFilter = filter;
        filteredData = filterData(allNemesisData);
        updateCharts(filteredData);
    }

    function toggleCollapsed() {
        collapsed = !collapsed;
        if (!collapsed  && !allNemesisData.length) {
            fetchData().then((data) => {
                if (!errorMsg) {
                    extractVersionsAndReleases(data);
                    filteredData = filterData(data);
                    updateCharts(filteredData);
                }
            });
        }
    }

    onMount(() => {
        collapsed = true;
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
                on:click={toggleCollapsed}
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
                            on:click={() => applyFilter("")}>All</button
                        >
                        {#each releases as release}
                            <button
                                class:active={selectedFilter === release}
                                class="btn btn-outline-secondary"
                                on:click={() => applyFilter(release)}>{release}</button
                            >
                        {/each}
                    </div>
                    <div class="btn-group mb-3" role="group">
                        {#each versions as version}
                            <button
                                class:active={selectedFilter === version}
                                class="btn btn-outline-primary btn-sm"
                                on:click={() => applyFilter(version)}>{version}</button
                            >
                        {/each}
                    </div>

                    <div class="row">
                        <div class="col-md-3">
                            <div class="small-chart-container mb-3">
                                <canvas bind:this={chartCanvas} />
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
                                <canvas bind:this={barChartCanvas} />
                            </div>
                        </div>
                    </div>
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
</style>
