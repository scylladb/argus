<script>
    import { faMarkdown } from "@fortawesome/free-brands-svg-icons";
    import { faInfoCircle } from "@fortawesome/free-solid-svg-icons";
    import { ResultCellStatusStyleMap } from "../../Common/TestStatus";
    import Cell from "./Cell.svelte";
    import Fa from "svelte-fa";
    import { sendMessage } from "../../Stores/AlertStore";

    export let table_name;
    export let result;
    export let selectedScreenshot;

    let showDescription = false;

    const tableStyleToColor = {
        "table-success": "green",
        "table-danger": "red",
        "table-warning": "yellow",
        "table-secondary": "gray",
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

    async function copyResultTableAsMarkdown(event) {
        const table = event.currentTarget.closest("table");
        let markdown = "";

        if (table) {
            const rows = Array.from(table.querySelectorAll("tr"));
            rows.forEach((row, rowIndex) => {
                const cells = Array.from(row.querySelectorAll("th, td"));
                const markdownRow = cells.map(cell => {
                    let cellText = cell.innerText.trim();
                    let link = "";

                    const linkElement = cell.querySelector("a");
                    const buttonElement = cell.querySelector("button");

                    if (linkElement) {
                        link = linkElement.href;
                    } else if (buttonElement) {
                        link = buttonElement.getAttribute("data-link");
                    }

                    cellText = cellText.replace(/#/g, "#&#8203;");

                    if (link) {
                        cellText = `[${cellText}](${link})`;
                    }

                    const color = styleToColor(cell.className);
                    if (color) {
                        cellText = `$$\{\\color{${color}}${cellText}}$$`;
                    }

                    return cellText;
                }).join(" | ");
                markdown += `| ${markdownRow} |\n`;

                if (rowIndex === 0) {
                    const separator = cells.map(() => "---").join(" | ");
                    markdown += `| ${separator} |\n`;
                }
            });

            try {
                await navigator.clipboard.writeText(markdown);
                sendMessage("info", "Table copied to clipboard in Markdown format!");
            } catch (err) {
                sendMessage("error", "Failed to copy: ", err);
            }
        }
    }

    function toggleDescription() {
        showDescription = !showDescription;
    }
</script>

<li class="result-item {result.table_status}">
    <div class="result-content">
        <div class="table-header">
            <h5>{table_name}</h5>
            <button class="btn btn-outline-secondary btn-sm p-1" on:click={toggleDescription}>
                <Fa icon={faInfoCircle} size="sm"/>
            </button>
        </div>
        {#if showDescription}
            <p class="table-description">{result.description}</p>
        {/if}
        <div class="table-responsive">
            <div class="table-container">
                <table class="table table-sm table-bordered">
                    <thead class="thead-dark">
                    <tr>
                        <th>
                            <button class="btn btn-outline-success btn-sm p-1" on:click={copyResultTableAsMarkdown}>
                                <Fa icon={faMarkdown} size="sm"/>
                            </button>
                        </th>
                        {#each result.columns as col}
                            <th>{col.name} <span class="unit">{col.unit ? `[${col.unit}]` : ''}</span></th>
                        {/each}
                    </tr>
                    </thead>
                    <tbody>
                    {#each result.rows as row}
                        <tr>
                            <td>{row}</td>
                            {#each result.columns as col}
                                {#key result.table_data[row][col.name]}
                                    <td class="{ResultCellStatusStyleMap[result.table_data[row][col.name]?.status || 'NULL']}">
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

    th, td {
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
</style>

