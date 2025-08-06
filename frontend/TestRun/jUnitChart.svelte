<script lang="ts">
    import { onMount } from "svelte";
    import { Chart, registerables } from "chart.js";

    let { results } = $props();

    const resultColors = {
        passed: "#198754",
        failure: "#dc3545",
        skipped: "#212529",
        error: "#ffc107",
        disabled: "#d3d4d5",
    };

    let canvas = $state();
    let chart = {
        data: {},
        update: () => {
            //empty
        },
    };

    const prepareChartedResults = function(results) {
        return results.reduce((acc, val) => {
            if (!acc[val.status]) acc[val.status] = 0;
            acc[val.status] += 1;
            return acc;
        }, {});
    };

    onMount(() => {
        let preparedResults = prepareChartedResults(results);
        let chartData = {
            labels: Object.keys(preparedResults),
            datasets: [{
                label: "Tests",
                data: Object.values(preparedResults),
                backgroundColor: Object.keys(preparedResults).map(v => resultColors[v]),
                barPercentage: 0.2,
            }]
        };

        Chart.register(...registerables);
        const chartContext = canvas.getContext("2d");
        chart = new Chart(chartContext, {
            type: "bar",
            data: chartData,
            options: {
                responsive: false,
                maintainAspectRatio: true
            }
        });
    });
</script>


<canvas bind:this={canvas} height="128px"></canvas>
