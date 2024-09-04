<script>
    import {Chart, registerables} from "chart.js";
    import {createEventDispatcher, onMount} from "svelte";
    import "chartjs-adapter-date-fns";

    export let graph = {};
    export let ticks = {};
    export let index = 0;
    export let test_id = "";
    export let width = 500;
    export let height = 300;
    let chart;
    const dispatch = createEventDispatcher();

    onMount(() => {
        Chart.register(...registerables);
        let actions = {
            onClick: (event, elements, chart) => {
                if (elements[0]) {
                    const dataset_idx = elements[0].datasetIndex;
                    const index = elements[0].index;
                    dispatch("runClick", {runId: chart.data.datasets[dataset_idx].data[index].id});
                }
            }
        };
        const xTicks = [...new Set(graph.data.datasets[0].data.map(point => point.x.slice(0, 10)))];
        graph.options.animation = false;
        graph.options.plugins.tooltip = {
            callbacks: {
                label: function (tooltipItem) {
                    const y = tooltipItem.parsed.y;
                    const x = new Date(tooltipItem.parsed.x).toLocaleDateString("sv-SE");
                    const ori = tooltipItem.raw.ori;
                    return `${x}: ${ori? ori : y}`;
                }
            }
        };
        graph.options.scales.x.min = ticks["min"];
        graph.options.scales.x.max = ticks["max"];
        graph.options.scales.x.ticks = {
            stepSize: 1,
            minRotation: 45,
            maxTicksLimit: 12,
            callback: function (value, index) {
                if (value == ticks["min"] || value == ticks["max"] || xTicks.includes(value)) {
                    return value;
                }
                return null;
            }
        };
        chart = new Chart(
            document.getElementById(`graph-${test_id}-${index}`),
            {type: "scatter", data: graph.data, options: {...graph.options, ...actions}}
        );
        return () => {
            chart.destroy();
            Chart.unregister(...registerables);
        };
    });

</script>

<canvas id="graph-{test_id}-{index}" width="{width}" height="{height}"></canvas>
