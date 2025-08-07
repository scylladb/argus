<script lang="ts">
    import { run } from 'svelte/legacy';

    import { Chart, registerables } from "chart.js";
    import { TestStatusColors as clMap } from "../Common/TestStatus.js";
    import { onMount } from "svelte";
    let { stats = {
        created: 0,
        running: 0,
        passed: 0,
        failed: 0,
        lastStatus: "unknown",
        total: -1,
    } } = $props();
    let chartCanvas = $state(undefined);
    let chart = $state({
        data: {},
        update: ()=>{}
    });
    let data = $state({});
    run(() => {
        data = {
            labels: ["Failed", "Aborted", "Passed", "Running", "Started", "Not Run"],
            datasets: [{
                label: "Test Statistics",
                data: [stats.failed, stats.aborted, stats.passed, stats.running, stats.created, stats.not_run],
                backgroundColor: [clMap.failed, clMap.aborted, clMap.passed, clMap.running, clMap.created, clMap.unknown]
            }]
        }
    });
    run(() => {
        chart.data = data;
    });
    run(() => {
        chart.update();
    });
    onMount(() => {
        Chart.register(...registerables);
        const chartContext = chartCanvas.getContext("2d");
        chart = new Chart(chartContext, {
            type: 'pie',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: true
            }
        });
    });

</script>
<canvas bind:this={chartCanvas} width="112px"></canvas>
