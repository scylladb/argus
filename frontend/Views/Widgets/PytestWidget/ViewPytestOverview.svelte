<script lang="ts">
    import { Chart } from "chart.js";
    import { onMount } from "svelte";
    import { titleCase } from "../../../Common/TextUtils";

    export let dashboardObject: Record<string, unknown>;
    /**
     * @type {string}
     */
    export let dashboardObjectType: string;
    export let stats: Record<string, unknown>;
    export let settings: Record<string, unknown>;
    export let productVersion: string;
    console.log("PytestOverview-Init");

    let pytestBarStatsCanvas: HTMLCanvasElement;
    let pytestBarChart: Chart;
    let pytestPieChartCanvas: HTMLCanvasElement;
    let pytestPieChart: Chart<"pie">;

    interface IRoutes {
        [key: string]: string;
    }

    interface PytestResult {
        duration: number;
        id: string;
        markers: string[];
        name: string;
        release_id: string;
        run_id: string;
        session_timestamp: string;
        status: string;
        test_id: string;
        test_timestamp: string;
        test_type: string;
        user_fields: Record<string, string>;
    }

    interface IStatusCount {
        [key: string]: number;
    }

    interface ITestStats {
        names: string[];
        pass: number[];
        fail: number[];
    }

    const ROUTES: IRoutes = {
        release: "/api/v1/release/$id/pytest/results",
        view: "/api/v1/views/$id/pytest/results",
    };

    let testData: PytestResult[] = [];

    const fetchPytestStats = async function () {
        try {
            const res = await fetch(ROUTES[dashboardObjectType].replace("$id", dashboardObject.id as string));
            const json = await res.json();

            testData = json.response;
            createBarChar(prepareTestStats(testData));
            createPieChart(testData);
        } catch (e) {
            // aa
        } finally {
            // bb
        }
    };

    const prepareTestStats = function (results: PytestResult[]): ITestStats {
        const mapped = results.reduce((acc: { [key: string]: { passed: number; failed: number } }, result) => {
            let results = acc[result.name] || { passed: 0, failed: 0 };
            results[result.status == "passed" ? "passed" : "failed"] += 1;
            acc[result.name] = results;
            return acc;
        }, {});
        console.log(mapped);
        return Object.entries(mapped).reduce(
            (acc, [name, counts]) => {
                acc.names.push(name);
                acc.pass.push(counts.passed);
                acc.fail.push(counts.failed);
                return acc;
            },
            { names: [], pass: [], fail: [] } as ITestStats
        );
    };

    const createPieChart = function (results: PytestResult[]) {
        if (pytestPieChart) {
            pytestPieChart.destroy();
        }

        let statusCounts = results.reduce((counts, result) => {
            let last = counts[result.status] || 0;
            counts[result.status] = last + 1;
            return counts;
        }, {} as IStatusCount);

        pytestPieChart = new Chart(pytestPieChartCanvas, {
            type: "pie",
            data: {
                labels: Object.keys(statusCounts),
                datasets: [
                    {
                        data: Object.values(statusCounts),
                        backgroundColor: ["rgb(75, 192, 192)", "rgb(255, 99, 132)"],
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: false,
                    },
                },
            },
        });
    };

    const createBarChar = function (testStats: ITestStats) {
        if (pytestBarChart) {
            pytestBarChart.destroy();
        }
        console.log(testData, testStats);
        pytestBarChart = new Chart(pytestBarStatsCanvas, {
            type: "bar",
            data: {
                labels: testStats.names,
                datasets: [
                    {
                        label: "Succeeded",
                        data: testStats.pass,
                        backgroundColor: "rgb(75, 192, 192)",
                    },
                    {
                        label: "Failed",
                        data: testStats.fail,
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
                        text: "Overview",
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
                    if (!event?.native?.target) return;
                    const canvas = event.native.target as HTMLCanvasElement;
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
                    // empty
                },
            },
        });
    };

    onMount(async () => {
        await fetchPytestStats();
    });
</script>

<div class="d-flex p-2">
    <div class="w-25">
        <canvas bind:this={pytestPieChartCanvas} />
    </div>
    <div class="ms-2 w-75">
        <canvas bind:this={pytestBarStatsCanvas} />
    </div>
</div>
<div class="w-100">
    {#if testData.length > 0}
        <div class="table-responsive table table-hover">
            <thead>
                <th>Test</th>
                <th> Data </th>
            </thead>
            <tbody>
                {#each testData as result}
                    <tr class="border-bottom">
                        <td class="fw-bold">{result.name}</td>
                        <table class="table-responsive table table-hover table-striped">
                            <thead>
                                <th>Key</th>
                                <th>Value</th>
                            </thead>
                            <tbody>
                                {#each Object.entries(result) as [key, value]}
                                    <tr class="table-striped">
                                        <td><span class="fw-bold">{titleCase(key.split("_").join(" "))}</span></td>
                                        <td>{JSON.stringify(value, undefined, 1)}</td>
                                    </tr>
                                {/each}
                            </tbody>
                        </table>
                    </tr>
                {/each}
            </tbody>
        </div>
    {/if}
</div>
