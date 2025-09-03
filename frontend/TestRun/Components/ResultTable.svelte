<script lang="ts">
    import {faMarkdown} from "@fortawesome/free-brands-svg-icons";
    import {faInfoCircle, faChartLine} from "@fortawesome/free-solid-svg-icons";
    import {ResultCellStatusStyleMap} from "../../Common/TestStatus";
    import Cell from "./Cell.svelte";
    import Fa from "svelte-fa";
    import {sendMessage} from "../../Stores/AlertStore";
    import ResultsGraph from "../ResultsGraph.svelte";
    import queryString from "query-string";
    import GraphFilters from "./GraphFilters.svelte";
    import ModalWindow from "../../Common/ModalWindow.svelte";

    let {
        table_name,
        result,
        selectedScreenshot = $bindable(),
        test_id
    } = $props();

    let showDescription = $state(false);
    let showGraphModal = $state(false);
    let graph = $state(null);
    let ticks = $state({});
    let releasesFilters = $state({});
    let selectedColumnName = $state("");
    let dateRange = $state(6);
    let startDate = "";
    let endDate = "";
    let redraw = $state(0);
    let resultTableElement = $state();

    const tableStyleToColor = {
        "table-success": "green",
        "table-danger": "red",
        "table-warning": "yellow",
        "table-secondary": "gray",
    };

    const dispatchRunClick = (e) => {
        const runId = e.detail.runId;
        window.open(`/tests/scylla-cluster-tests/${runId}`, "_blank", "popup");
    };

    function styleToColor(classList) {
        const classes = classList.split(" ");
        for (let className of classes) {
            if (className.startsWith("table-") && tableStyleToColor[className]) {
                return tableStyleToColor[className];
            }
        }
        return "";
    }

    export async function copyResultTableAsMarkdown(mode = "clipboard") {
        if (!resultTableElement) return;
        const table = resultTableElement;
        let markdown = "";

        if (table) {
            const rows = Array.from(table.querySelectorAll("tr"));
            rows.forEach((row, rowIndex) => {
                const cells = Array.from(row.querySelectorAll("th, td"));
                const markdownRow = cells
                    .map((cell) => {
                        let cellText = cell.innerText;
                        let link = "";

                        const linkElement = cell.querySelector("a");
                        const buttonElement = cell.querySelector("button");

                        if (linkElement) {
                            link = linkElement.href;
                        } else if (buttonElement) {
                            link = buttonElement.getAttribute("data-link");
                        }

                        cellText = cellText.replace(/\|/g, "\\|");
                        cellText = cellText.replace(/\s+/g, " ").trim();
                        cellText = cellText.replace(/#/g, "#&#8203;");

                        if (link) {
                            cellText = `[${cellText}](${link})`;
                        }

                        const color = styleToColor(cell.className);
                        if (color) {
                            cellText = `$$\{\\color{${color}}${cellText}}$$`;
                        }

                        return cellText;
                    })
                    .join(" | ");
                markdown += `| ${markdownRow} |\n`;

                if (rowIndex === 0) {
                    const separator = cells.map(() => "---").join(" | ");
                    markdown += `| ${separator} |\n`;
                }
            });

            if (mode === "clipboard") {
                try {
                    await navigator.clipboard.writeText(markdown);
                    sendMessage("info", "Table copied to clipboard in Markdown format!");
                } catch (err) {
                    sendMessage("error", "Failed to copy: ", err);
                }
            } else if (mode === "string") {
                return Promise.resolve(markdown);
            }
        }
    }

    function toggleDescription() {
        showDescription = !showDescription;
    }

    async function fetchGraphData() {
        try {
            const params = queryString.stringify({
                testId: test_id,
                startDate,
                endDate,
                "tableNames[]": [table_name],
            });

            let res = await fetch(`/api/v1/test-results?${params}`);
            if (res.status !== 200) {
                throw new Error(`HTTP Error ${res.status} trying to fetch test results`);
            }
            let results = await res.json();
            if (results.status !== "ok") {
                throw new Error(`API Error: ${results.message}`);
            }

            const response = results["response"];
            if (!response.graphs || response.graphs.length === 0) {
                throw new Error("No graph data available for this table");
            }

            graph = response["graphs"].find((graph) => graph.options.plugins.title.text.endsWith(selectedColumnName));
            ticks = response["ticks"];
            releasesFilters = Object.fromEntries(response["releases_filters"].map((key) => [key, true]));
        } catch (error) {
            console.log("Error:", error);
            sendMessage("error", `Failed to load graph data: ${error.message}`);
        }
    }

    async function openGraphModal(columnName = "") {
        selectedColumnName = columnName;
        showGraphModal = true;
    }

    function closeGraphModal() {
        showGraphModal = false;
        graph = null;
        selectedColumnName = "";
    }

    async function handleDateChange(event) {
        startDate = event.detail.startDate;
        endDate = event.detail.endDate;
        if (showGraphModal) {
            await fetchGraphData();
            redraw++;
        }
    }

    async function handleReleaseChange(event) {
        releasesFilters = event.detail.releasesFilters;
        redraw++;
    }
</script>

<li class="result-item {result.table_status}">
    <div class="result-content">
        <div class="table-header">
            <h5>{table_name}</h5>
            <button class="btn btn-link p-0 ms-1" onclick={toggleDescription}>
                <Fa icon={faInfoCircle} size="sm"/>
            </button>
        </div>
        {#if showDescription}
            <p class="table-description">{result.description}</p>
        {/if}
        <div class="table-responsive">
            <div class="table-container">
                <table bind:this={resultTableElement} class="table table-sm table-bordered">
                    <thead class="thead-dark">
                    <tr>
                        <th>
                            <button class="btn btn-link p-1" onclick={async () => await copyResultTableAsMarkdown()}>
                                <Fa icon={faMarkdown} size="sm"/>
                            </button>
                        </th>
                        {#each result.columns as col}
                            {#if col.type !== "TEXT"}
                                <th class="clickable" onclick={() => openGraphModal(col.name)} title="Show metric history">
                                    <div class="column-header">
                                        {col.name}<span
                                            class="unit">{col.unit ? `[${col.unit}]` : ""}</span>
                                    </div>
                                </th>
                            {:else}
                                <th>
                                    <div class="column-header">{col.name}</div>
                                </th>
                            {/if}
                        {/each}
                    </tr>
                    </thead>
                    <tbody>
                    {#each result.rows as row}
                        <tr>
                            <td>{row}</td>
                            {#each result.columns as col}
                                {#key result.table_data[row][col.name]}
                                    <td
                                            class={ResultCellStatusStyleMap[
                                                result.table_data[row][col.name]?.status || "NULL"
                                            ]}
                                    >
                                        <Cell cell={result.table_data[row][col.name]} bind:selectedScreenshot/>
                                    </td>
                                {/key}
                            {/each}
                        </tr>
                    {/each}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</li>

{#if showGraphModal}
    <ModalWindow widthClass="w-75" on:modalClose={closeGraphModal}>
        {#snippet title()}
                <div >
                {table_name}
                {selectedColumnName ? `- ${selectedColumnName}` : ""}
            </div>
            {/snippet}
        {#snippet body()}
                <div  style="min-height: 800px;">
                <GraphFilters
                        bind:dateRange
                        bind:releasesFilters
                        on:dateChange={handleDateChange}
                        on:releaseChange={handleReleaseChange}
                />
                {#if graph}
                    {#key redraw}
                        <ResultsGraph
                                {graph}
                                {ticks}
                                {test_id}
                                width={1400}
                                height={700}
                                {releasesFilters}
                                responsive={true}
                                on:runClick={dispatchRunClick}
                        />
                    {/key}
                {/if}
            </div>
            {/snippet}
    </ModalWindow>
{/if}

<style>
    .result-item {
        margin-bottom: 1rem;
        display: flex;
        font-size: 0.9rem;
    }

    .result-item::before {
        content: "";
        display: block;
        width: 3px;
        background-color: #ddd;
        margin-right: 0.5rem;
        border-radius: 1px;
    }

    .result-item.PASS::before {
        background-color: var(--bs-success) !important;
    }

    .result-item.ERROR::before {
        background-color: var(--bs-danger) !important;
    }

    .result-content {
        flex-grow: 1;
    }

    .table-header {
        display: flex;
        align-items: center;
        margin-bottom: 0.25rem;
    }

    .table-header h5 {
        margin: 0;
        margin-right: 0.5rem;
        font-size: 1rem;
    }

    .table-description {
        margin-bottom: 0.5rem;
        font-style: italic;
        color: #666;
        font-size: 0.85rem;
    }

    .table-responsive {
        display: flex;
        /*justify-content: center;*/
    }

    .table-container {
        max-width: fit-content;
    }

    table {
        width: auto;
        min-width: 100%;
        table-layout: auto;
        font-size: 0.85rem;
    }

    th,
    td {
        text-align: center;
        padding: 0.25rem !important;
    }

    .unit {
        font-size: 0.75em;
        color: gray;
        vertical-align: top;
    }

    :global(.btn-sm) {
        font-size: 0.75rem;
    }

    .column-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
    }

    .column-header button {
        opacity: 0.6;
    }

    .column-header button:hover {
        opacity: 1;
    }

    .clickable {
        text-decoration: underline;
        cursor: pointer;
    }
</style>
