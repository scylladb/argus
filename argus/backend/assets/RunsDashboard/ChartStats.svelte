<script>
    import { Chart, registerables } from "chart.js";
    import { TestStatusColors as clMap } from "./TestStatus.js";
    import { onMount } from "svelte";
    export let stats = {
        created: 0,
        running: 0,
        passed: 0,
        failed: 0,
        lastStatus: "unknown",
        total: -1,
    };
    let chartCanvas = undefined;
    let chart = {
        data: {},
        update: ()=>{}
    };
    let data = {};
    $: data = {
        labels: ["Failed", "Aborted", "Passed", "Running", "Started", "Not Run"],
        datasets: [{
            label: "Test Statistics",
            data: [stats.failed, stats.aborted, stats.passed, stats.running, stats.created, stats.not_run],
            backgroundColor: [clMap.failed, clMap.aborted, clMap.passed, clMap.running, clMap.created, clMap.unknown]
        }]
    }
    $: chart.data = data;
    $: chart.update();
    onMount(() => {
        Chart.register(...registerables);
        const chartContext = chartCanvas.getContext("2d");
        chart = new Chart(chartContext, {
            type: 'pie',
            data: data
        });
    });

</script>
<div>
    <canvas width=512 height=512 bind:this={chartCanvas}></canvas>
</div>
<div class="text-center">Total: {stats.total}</div>