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
    export let releasesFilters = {};
    let chart;
    const ticksGapPx = 40;
    const dispatch = createEventDispatcher();

    function calculateTickValues(xValues, width, minGapInPixels) {
        // trying to calculate the best tick values for x-axis - to be evenly distributed as possible but matching actual points
        const xValuesUnique = [...new Set(xValues)].sort((a, b) => new Date(a) - new Date(b));
        let tickValues = [];
        let currentIndex = 0;
        tickValues.push(xValuesUnique[currentIndex]);

        const totalWidthInPixels = width;
        const totalTimeRange = new Date(xValuesUnique[xValuesUnique.length - 1]) - new Date(xValuesUnique[0]);
        const pixelsPerDay = totalWidthInPixels / totalTimeRange;
        const minGapInDays = minGapInPixels / pixelsPerDay;

        while (currentIndex < xValuesUnique.length - 1) {
            let nextIndex = currentIndex + 1;
            while (nextIndex < xValuesUnique.length && (new Date(xValuesUnique[nextIndex]) - new Date(xValuesUnique[currentIndex])) < minGapInDays) {
                nextIndex++;
            }
            if (nextIndex < xValuesUnique.length) {
                tickValues.push(xValuesUnique[nextIndex]);
            }
            currentIndex = nextIndex;
        }

        if (tickValues.length > 1 && (new Date(xValuesUnique[xValuesUnique.length - 1]) - new Date(tickValues[tickValues.length - 2])) < minGapInDays) {
            tickValues[tickValues.length - 1] = xValuesUnique[xValuesUnique.length - 1];
        } else if (tickValues[tickValues.length - 1] !== xValuesUnique[xValuesUnique.length - 1]) {
            tickValues.push(xValuesUnique[xValuesUnique.length - 1]);
        }

        return tickValues;
    }

    onMount(() => {
        Chart.register(...registerables);

        if (Object.values(releasesFilters).includes(false)) {
            // filter datasets based on releases filters
            graph = {...graph, data: {...graph.data, datasets: [...graph.data.datasets]}};
            graph.data.datasets = graph.data.datasets.filter(dataset => {
                const releaseLabel = dataset.label.split(' -')[0];
                return releasesFilters[releaseLabel] !== false;
            });
        }

        let actions = {
            onClick: (event, elements, chart) => {
                if (elements[0]) {
                    const dataset_idx = elements[0].datasetIndex;
                    const index = elements[0].index;
                    dispatch("runClick", {runId: chart.data.datasets[dataset_idx].data[index].id});
                }
            }
        };
        const xValues = graph.data.datasets.flatMap(dataset => dataset.data.map(point => point.x.slice(0, 10)));
        const tickValues = calculateTickValues(xValues, width, ticksGapPx);

        graph.options.animation = false;
        graph.options.responsive = false;
        graph.options.lazy = true;
        graph.options.plugins.tooltip = {
            callbacks: {
                label: function (tooltipItem) {
                    const y = tooltipItem.parsed.y.toFixed(2);
                    const x = new Date(tooltipItem.parsed.x).toLocaleDateString("sv-SE");
                    const ori = tooltipItem.raw.ori;
                    const limit = tooltipItem.raw.limit;
                    return `${x}: ${ori ? ori : y} (limit: ${limit?.toFixed(2) || "N/A"})`;
                }
            }
        };
        graph.options.scales.x.min = ticks["min"];
        graph.options.scales.x.max = ticks["max"];
        graph.options.scales.x.ticks = {
            minRotation: 45,
            callback: function (value, index) {
                if (tickValues.includes(value)) {
                    return value;
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
