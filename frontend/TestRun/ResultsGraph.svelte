<script lang="ts">
    import { run, createBubbler, stopPropagation } from 'svelte/legacy';

    const bubble = createBubbler();
    import { Chart, registerables, Tooltip } from "chart.js";
    import { createEventDispatcher, onDestroy, onMount } from "svelte";
    import "chartjs-adapter-date-fns";
    import {faExpand, faCopy} from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import {sendMessage} from "../Stores/AlertStore";

    interface Props {
        graph?: any;
        ticks?: any;
        index?: number;
        test_id?: string;
        width?: number;
        height?: number;
        responsive?: boolean;
        releasesFilters?: any;
    }

    let {
        graph = $bindable({}),
        ticks = {},
        index = 0,
        test_id = "",
        width = 500,
        height = 350,
        responsive = false,
        releasesFilters = {}
    }: Props = $props();
    let chart;
    let showModal = $state(false);
    let modalChart = $state();
    let activeTooltip = null;

    function openModal() {
        showModal = true;
        window.addEventListener("keydown", handleKeydown);
    }

    function closeModal() {
        activeTooltip = null;
        showModal = false;
        if (modalChart) {
            modalChart.destroy();
            modalChart = null;
        }
        const tooltipEl = document.getElementById("chartjs-tooltip");
        if (tooltipEl) {
            tooltipEl.remove();
        }
        window.removeEventListener("keydown", handleKeydown);
    }

    function handleKeydown(event: KeyboardEvent) {
        if (event.key === "Escape") {
            closeModal();
        }
    }

    async function copyToClipboard() {
        try {
            const canvasId = showModal ? `modal-graph-${test_id}-${index}` : `graph-${test_id}-${index}`;
            const canvas = document.getElementById(canvasId);
            const dataUrl = canvas.toDataURL("image/png");

            // Convert dataUrl to Blob
            const res = await fetch(dataUrl);
            const blob = await res.blob();

            // eslint-disable-next-line no-undef
            const item = new ClipboardItem({"image/png": blob});
            await navigator.clipboard.write([item]);

            sendMessage("success", "Graph copied to clipboard");
        } catch (error) {
            console.error("Error copying to clipboard:", error);
            sendMessage("error", "Failed to copy graph to clipboard");
        }
    }

    onDestroy(() => {
        window.removeEventListener("keydown", handleKeydown);
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
            while (
                nextIndex < xValuesUnique.length &&
                new Date(xValuesUnique[nextIndex]) - new Date(xValuesUnique[currentIndex]) < minGapInDays
            ) {
                nextIndex++;
            }
            if (nextIndex < xValuesUnique.length) {
                tickValues.push(xValuesUnique[nextIndex]);
            }
            currentIndex = nextIndex;
        }

        if (
            tickValues.length > 1 &&
            new Date(xValuesUnique[xValuesUnique.length - 1]) - new Date(tickValues[tickValues.length - 2]) <
                minGapInDays
        ) {
            tickValues[tickValues.length - 1] = xValuesUnique[xValuesUnique.length - 1];
        } else if (tickValues[tickValues.length - 1] !== xValuesUnique[xValuesUnique.length - 1]) {
            tickValues.push(xValuesUnique[xValuesUnique.length - 1]);
        }

        return tickValues;
    }

    function formatSecondsToHHMMSS(seconds: number) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    }

    function handleChartClick(event, elements, chart) {
        if (elements[0]) {
            const dataset_idx = elements[0].datasetIndex;
            const index = elements[0].index;
            activeTooltip = { datasetIndex: dataset_idx, index: index };
        } else {
            // Clicked outside points - clear tooltip
            activeTooltip = null;
            const tooltipEl = document.getElementById("chartjs-tooltip");
            if (tooltipEl) tooltipEl.remove();
        }
    }

    onMount(() => {
        Chart.register(...registerables);

        if (Object.values(releasesFilters).includes(false)) {
            // filter datasets based on releases filters
            graph = { ...graph, data: { ...graph.data, datasets: [...graph.data.datasets] } };
            graph.data.datasets = graph.data.datasets.filter((dataset) => {
                const releaseLabel = dataset.label.split(" -")[0];
                return releasesFilters[releaseLabel] !== false;
            });
        }

        let actions = {
            onClick: handleChartClick,
        };
        const xValues = graph.data.datasets.flatMap((dataset) => dataset.data.map((point) => point.x.slice(0, 10)));
        const tickValues = calculateTickValues(xValues, width, ticksGapPx);

        graph.options.animation = false;
        graph.options.responsive = responsive;
        graph.options.lazy = true;
        graph.options.plugins.tooltip = {
            enabled: false,
            mode: "point",
            intersect: true,
            position: "above",
            external: function (context) {
                if (activeTooltip) {
                    return;
                }
                let tooltipEl = document.getElementById("chartjs-tooltip");
                if (!tooltipEl) {
                    tooltipEl = document.createElement("div");
                    tooltipEl.id = "chartjs-tooltip";
                    tooltipEl.innerHTML = "<div></div>";
                    document.body.appendChild(tooltipEl);
                }

                const tooltipModel = context.tooltip;
                if (tooltipModel.opacity === 0 && !activeTooltip) {
                    tooltipEl.remove();
                    return;
                }

                if (tooltipModel.body) {
                    const titleLines = tooltipModel.title || [];
                    const bodyLines = tooltipModel.body.map((b) => b.lines);

                    let innerHtml = '<div class="custom-tooltip">';

                    tooltipModel.dataPoints.forEach((dataPoint, i) => {
                        const colors = tooltipModel.labelColors[i];
                        const pointStyle = tooltipModel.labelPointStyles[i];

                        const span = document.createElement("span");
                        span.style.display = "inline-block";
                        span.style.width = "10px";
                        span.style.height = "10px";
                        span.style.marginRight = "8px";
                        span.style.borderRadius = "50%";
                        span.style.backgroundColor = colors.backgroundColor;
                        span.style.border = `2px solid ${colors.borderColor}`;

                        // Add title
                        innerHtml += `<div class="tooltip-title">`;
                        innerHtml += span.outerHTML;
                        innerHtml += titleLines[i];
                        innerHtml += `</div>`;

                        // Add corresponding changes
                        const changes = tooltipModel.body[i]?.lines || [];
                        changes.forEach((line: string) => {
                            innerHtml += `<div class="tooltip-body">${line}</div>`;
                        });

                        const runId = context.chart.data.datasets[dataPoint.datasetIndex].data[dataPoint.dataIndex].id;
                        innerHtml += `<div class="d-flex justify-content-end mt-2">`;
                        innerHtml += `<a href="/tests/scylla-cluster-tests/${runId}" class="btn btn-success btn-sm" target="_blank">Open <i class="fas fa-external-link-alt"></i></a>`;
                        innerHtml += `</div>`;

                        // Add separator between points if not the last one
                        if (i < tooltipModel.dataPoints.length - 1) {
                            innerHtml += '<hr class="tooltip-separator">';
                        }
                    });

                    innerHtml += "</div>";
                    tooltipEl.innerHTML = innerHtml;
                }

                const position = context.chart.canvas.getBoundingClientRect();

                // Display, position, and set styles for font
                tooltipEl.style.position = "absolute";
                tooltipEl.style.left = position.left + window.scrollX + tooltipModel.caretX + "px";
                tooltipEl.style.top = position.top + window.scrollY + tooltipModel.caretY + "px";
                tooltipEl.style.backgroundColor = "rgba(0, 0, 0, 0.8)";
                tooltipEl.style.color = "#fff";
                tooltipEl.style.borderRadius = "3px";
                tooltipEl.style.transform = "translate(-50%, -100%)";
            },
            callbacks: {
                title: function (tooltipItems) {
                    return tooltipItems.map((item) => {
                        const yValue = item.parsed.y;
                        const limitValue = item.raw.limit;
                        const isHHMMSS = graph.options.scales.y.title?.text?.includes("[HH:MM:SS]");
                        const formattedY = isHHMMSS ? formatSecondsToHHMMSS(yValue) : yValue.toFixed(2);
                        const formattedLimit =
                            isHHMMSS && limitValue !== undefined
                                ? formatSecondsToHHMMSS(limitValue)
                                : limitValue?.toFixed(2) || "N/A";

                        const x = new Date(item.parsed.x).toLocaleDateString("sv-SE");
                        const ori = item.raw.ori;
                        return `${x}: ${ori ? ori : formattedY} (error threshold: ${formattedLimit})`;
                    });
                },
                label: function (tooltipItem) {
                    return tooltipItem.raw.changes || [];
                },
            },
        };
        graph.options.scales.x.min = ticks["min"];
        graph.options.scales.x.ticks = {
            minRotation: 45,
            callback: function (value, index) {
                if (tickValues.includes(value)) {
                    return value;
                }
            },
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
                point.dep_change ? "white" : dataset.backgroundColor || dataset.borderColor
            );
            dataset.pointBackgroundColor = pointBackgroundColors;
        });

        let elem = document.getElementById(`graph-${test_id}-${index}`) as HTMLCanvasElement;
        if (!elem) return;

        chart = new Chart(elem, {
            type: "scatter",
            data: $state.snapshot(graph.data),
            options: { ...$state.snapshot(graph.options), ...actions },
        });

        return () => {
            chart.destroy();
            if (modalChart) {
                modalChart.destroy();
                modalChart = null;
            }
            // Remove tooltip element on component destroy
            const tooltipEl = document.getElementById("chartjs-tooltip");
            if (tooltipEl) {
                tooltipEl.remove();
            }
            Chart.unregister(...registerables);
            window.removeEventListener("keydown", handleKeydown);
        };
    });

    $effect(() => {
        if (showModal) {
            let actions = {
                onClick: handleChartClick,
            };
            setTimeout(() => {
                const modalCanvas = document.getElementById(`modal-graph-${test_id}-${index}`);
                if (modalCanvas) {
                    modalChart = new Chart(modalCanvas, {
                        type: "scatter",
                        data: $state.snapshot(graph.data),
                        options: { ...$state.snapshot(graph.options), responsive: true, maintainAspectRatio: false, ...actions },
                    });
                }
            }, 0);
        }
    });
</script>

<div class="graph-container">
    <button class="copy-btn" onclick={copyToClipboard}>
        <Fa icon={faCopy}/>
    </button>
    <button class="enlarge-btn" onclick={openModal}>
        <Fa icon={faExpand}/>
    </button>
    <canvas id="graph-{test_id}-{index}" {width} {height}></canvas>
</div>

{#if showModal}
    <div class="modal">
        <div class="modal-content" onclick={stopPropagation(bubble('click'))}>
            <button class="close-btn" onclick={closeModal}>&times;</button>
            <button class="modal-copy-btn" onclick={() => copyToClipboard(true)}>
                <Fa icon={faCopy}/>
            </button>
            <canvas id="modal-graph-{test_id}-{index}"></canvas>
        </div>
    </div>
{/if}

<style>
    .graph-container {
        position: relative;
    }

    .enlarge-btn, .copy-btn {
        position: absolute;
        top: 10px;
        background: none;
        border: none;
        cursor: pointer;
        color: #888;
        font-size: 1.2em;
    }

    .enlarge-btn {
        right: 10px;
    }

    .copy-btn {
        right: 40px;
    }

    .enlarge-btn:hover, .copy-btn:hover {
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

    .modal-copy-btn {
        position: absolute;
        top: 10px;
        right: 40px;
        background: none;
        border: none;
        cursor: pointer;
        color: #888;
        font-size: 1.2em;
    }

    .modal-copy-btn:hover {
        color: #333;
    }

    canvas {
        max-width: 100%;
        max-height: 100%;
    }

    :global(#chartjs-tooltip) {
        z-index: 10000;
    }

    :global(.custom-tooltip) {
        min-width: 200px;
        margin: 4px;
    }

    :global(.tooltip-title) {
        margin-bottom: 8px;
        font-weight: bold;
        display: flex;
        align-items: center;
    }

    :global(.tooltip-title span) {
        flex-shrink: 0;
    }

    :global(.tooltip-body) {
        margin-bottom: 4px;
    }

    :global(.tooltip-separator) {
        border: none;
        height: 1px;
        background-color: #ccc;
        margin: 8px 0;
    }
</style>
