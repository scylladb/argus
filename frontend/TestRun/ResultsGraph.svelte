<script>
    import {Chart, registerables, Tooltip} from "chart.js";
    import {createEventDispatcher, onDestroy, onMount} from "svelte";
    import "chartjs-adapter-date-fns";
    import {faExpand} from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";

    export let graph = {};
    export let ticks = {};
    export let index = 0;
    export let test_id = "";
    export let width = 500;
    export let height = 300;
    export let releasesFilters = {};
    let chart;
    let showModal = false;
    let modalChart;

    function openModal() {
        showModal = true;
        window.addEventListener('keydown', handleKeydown);
    }

    function closeModal() {
        showModal = false;
        if (modalChart) {
            modalChart.destroy();
        }
        window.removeEventListener('keydown', handleKeydown);
    }

    function handleKeydown(event) {
        if (event.key === 'Escape') {
            closeModal();
        }
    }

    onDestroy(() => {
        window.removeEventListener('keydown', handleKeydown);
    });

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

    function formatSecondsToHHMMSS(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
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
                    const yValue = tooltipItem.parsed.y;
                    const limitValue = tooltipItem.raw.limit;
                    const isHHMMSS = graph.options.scales.y.title?.text?.includes("[HH:MM:SS]");
                    const formattedY = isHHMMSS ? formatSecondsToHHMMSS(yValue) : yValue.toFixed(2);
                    const formattedLimit = isHHMMSS && limitValue !== undefined
                        ? formatSecondsToHHMMSS(limitValue)
                        : limitValue?.toFixed(2) || "N/A";

                    const x = new Date(tooltipItem.parsed.x).toLocaleDateString("sv-SE");
                    const ori = tooltipItem.raw.ori;
                    const changes = tooltipItem.raw.changes;
                    return [`${x}: ${ori ? ori : formattedY} (error threshold: ${formattedLimit})`, ...changes];
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
        graph.options.scales.y.title = graph.options.scales.y.title || {};
        graph.options.scales.y.ticks = {
            callback: function (value) {
                if (graph.options.scales.y.title?.text?.includes("[HH:MM:SS]")) {
                    return formatSecondsToHHMMSS(value);
                }
                return value;
            },
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
            if (modalChart) {
                modalChart.destroy();
            }
            Chart.unregister(...registerables);
            window.removeEventListener('keydown', handleKeydown);
        };
    });

    $: if (showModal) {
        setTimeout(() => {
            const modalCanvas = document.getElementById(`modal-graph-${test_id}-${index}`);
            if (modalCanvas) {
                modalChart = new Chart(
                    modalCanvas,
                    {
                        type: "scatter",
                        data: graph.data,
                        options: {...graph.options, responsive: true, maintainAspectRatio: false}
                    }
                );
            }
        }, 0);
    }

</script>

<div class="graph-container">
    <button class="enlarge-btn" on:click={openModal}>
        <Fa icon={faExpand}/>
    </button>
    <canvas id="graph-{test_id}-{index}" width="{width}" height="{height}"></canvas>
</div>

{#if showModal}
    <div class="modal" on:click={closeModal}>
        <div class="modal-content" on:click|stopPropagation>
            <button class="close-btn" on:click={closeModal}>&times;</button>
            <canvas id="modal-graph-{test_id}-{index}"></canvas>
        </div>
    </div>
{/if}

<style>
    .graph-container {
        position: relative;
    }

    .enlarge-btn {
        position: absolute;
        top: 10px;
        right: 10px;
        background: none;
        border: none;
        cursor: pointer;
        color: #888;
        font-size: 1.2em;
    }

    .enlarge-btn:hover {
        color: #333;
    }

    .modal {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(0, 0, 0, 0.7);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
    }

    .modal-content {
        background-color: white;
        padding: 20px;
        border-radius: 5px;
        width: 90%;
        height: 90%;
        position: relative;
    }

    .close-btn {
        position: absolute;
        top: 10px;
        right: 10px;
        background: none;
        border: none;
        font-size: 1.5em;
        cursor: pointer;
    }

    canvas {
        max-width: 100%;
        max-height: 100%;
    }
</style>
