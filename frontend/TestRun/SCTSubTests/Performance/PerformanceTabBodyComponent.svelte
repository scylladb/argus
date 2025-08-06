<script lang="ts">
    import { onMount } from "svelte";
    import { sendMessage } from "../../../Stores/AlertStore";
    import { getScyllaPackage } from "../../../Common/RunUtils";

    let { testRun } = $props();
    let performanceResults;
    let performanceHistory = [];
    let resultsByVersion = $state();

    const MONITORED_METRICS = [
        "perf_op_rate_total",
        "perf_avg_latency_mean",
        "perf_avg_latency_99th",
    ];

    const asc = (a, b) => a - b;
    const desc = (a, b) => b - a;

    const METRIC_ORDER = {
        perf_op_rate_total: desc,
        perf_avg_latency_mean: asc,
        perf_avg_latency_99th: asc,
    };

    const fetchPerformanceHistory = async function () {
        try {
            let response = await fetch(`/api/v1/client/sct/${testRun.id}/performance/history`);
            let json = await response.json();
            if (json.status == "ok") {
                performanceHistory = json.response;
                resultsByVersion = sortResultsByVersion(performanceHistory);
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching test run data.\nMessage: ${error.response.arguments[0]}`,
                    "PerformanceTabBodyComponent::fetchPerformanceHistory"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test run data fetch",
                    "PerformanceTabBodyComponent::fetchPerformanceHistory"
                );
                console.log(error);
            }
        }
    };

    /**
     *
     * @param {Object[]} historicalData
     */
    const sortResultsByVersion = function(historicalData) {
        return historicalData.reduce((acc, run) => {
            if (!run.scylla_version) return acc;
            if (!acc[run.scylla_version]) acc[run.scylla_version] = [];
            acc[run.scylla_version].push(run);
            acc[run.scylla_version].sort((a, b) => Date.parse(b.start_time) - Date.parse(a.start_time));
            return acc;
        }, {});
    };

    const cmp = function(lhs, rhs) {
        const delta = rhs - lhs;
        const change = (Math.abs(delta) * 100 / rhs).toFixed(0);

        return delta >= 0 ? change : change * -1;
    };

    /**
     *
     * @param {{[key: string]: Object[]}} sortedHistoricalData
     * @param {string} metricName
     */
    const findBestAndLastResult = function(sortedHistoricalData, metricName) {
        let resultPerKey = {};
        for (let key in sortedHistoricalData) {
            let bestResult = Array.from(sortedHistoricalData[key]).sort((a, b) => METRIC_ORDER[metricName](a[metricName], b[metricName])).at(0);
            let lastResult = sortedHistoricalData[key].at(0);
            resultPerKey[key] = {
                "best": bestResult,
                "last": lastResult,
            };
        }

        return resultPerKey;
    };

    onMount(() => {
        fetchPerformanceHistory();
    });
</script>

<div
    class="tab-pane fade"
    id="nav-performance-{testRun.id}"
    role="tabpanel"
>
    <div class="p-2">
        <div class="mb-2 p-2">
            <h5>Performance</h5>
            <ul class="border-start list-unstyled p-2">
                <li><span class="fw-bold">Test name: </span>{testRun.test_name}</li>
                <li><span class="fw-bold">Stress command: </span>{testRun.stress_cmd}</li>
                <li><span class="fw-bold">Operation Rate: </span>{testRun.perf_op_rate_total}</li>
                <li><span class="fw-bold">Average Operation Rate: </span>{testRun.perf_op_rate_average}</li>
                <li><span class="fw-bold">Latency 99th Percentile: </span>{testRun.perf_avg_latency_99th}</li>
                <li><span class="fw-bold">Mean Latency: </span>{testRun.perf_avg_latency_mean}</li>
                <li><span class="fw-bold">Total Errors: </span>{testRun.perf_total_errors}</li>
            </ul>
        </div>
        <div class="p-2">
            {#each MONITORED_METRICS as metricName}
                {@const resultsByMetric = findBestAndLastResult(resultsByVersion, metricName)}
                <h2>{metricName.slice("perf_".length)}</h2>
                <div class="mb-2">
                    <table class="table table-bordered">
                        <thead>
                            <tr>
                                <th>Current Result</th>
                                <th>Compared Version</th>
                                <th>Best</th>
                                <th>Diff</th>
                                <th>Commit, Date</th>
                                <th>last</th>
                                <th>Diff</th>
                                <th>Commit, Date</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each Object.entries(resultsByMetric) as [versionName, results] (versionName)}
                                {@const bestPackage = getScyllaPackage(results.best.packages)}
                                {@const lastPackage = getScyllaPackage(results.last.packages)}
                                {@const cmpToBest = cmp(testRun[metricName], results.best[metricName])}
                                {@const cmpToLast = cmp(testRun[metricName], results.last[metricName])}
                                <tr>
                                    <td>{testRun[metricName].toFixed(1)}</td>
                                    <td>{versionName}</td>
                                    <td>{results.best[metricName].toFixed(1)}</td>
                                    <td class="table-{cmpToBest > 5 ? "success" : cmpToBest < -5 ? "danger" : "dark"}">{cmpToBest}%</td>
                                    <td>#{bestPackage.revision_id}, {bestPackage.date}</td>
                                    <td>{results.last[metricName].toFixed(1)}</td>
                                    <td class="table-{cmpToLast > 5 ? "success" : cmpToBest < -5 ? "danger" : "dark"}">{cmpToLast}%</td>
                                    <td>#{lastPackage.revision_id}, {lastPackage.date}</td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            {/each}
        </div>
    </div>
</div>
