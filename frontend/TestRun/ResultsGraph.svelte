<script>
    import {Chart, registerables, Tooltip} from "chart.js";
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
    Tooltip.positioners.above = function (elements, eventPosition) {
        const tooltip = this;
        if (elements.length === 0) {
            return false;
        }
        return {
            x: elements[0].element.x,
            y: elements[0].element.y - tooltip.height / 2 - 5,
            xAlign: "center",
            yAlign: "center",
        };
    };

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
            position: "above",
            usePointStyle: true,
            bodyFont: {
                size: 16,
                family: 'sans-serif',
            },
            callbacks: {
                label: function (tooltipItem) {
                    const y = tooltipItem.parsed.y.toFixed(2);
                    const x = new Date(tooltipItem.parsed.x).toLocaleDateString("sv-SE");
                    const ori = tooltipItem.raw.ori;
                    const limit = tooltipItem.raw.limit;
                    const changes = tooltipItem.raw.changes;
                    return [`${x}: ${ori ? ori : y} (error threshold: ${limit?.toFixed(2) || "N/A"})`, ...changes];
                },
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

        graph.data.datasets.forEach((dataset) => {
            const pointBackgroundColors = dataset.data.map((point) =>
                point.dep_change ? 'white' : dataset.backgroundColor || dataset.borderColor
            );
            dataset.pointBackgroundColor = pointBackgroundColors;
        });

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
