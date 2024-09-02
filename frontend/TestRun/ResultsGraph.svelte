<script>
    import {Chart, registerables} from "chart.js";
    import {createEventDispatcher, onDestroy, onMount} from "svelte";
    import "chartjs-adapter-date-fns";

    export let graph = {};
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
