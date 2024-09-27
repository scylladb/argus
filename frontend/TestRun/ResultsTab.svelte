<script>
    import {onMount} from "svelte";
    import {ResultCellStatusStyleMap} from "../Common/TestStatus";
    import {faMarkdown} from "@fortawesome/free-brands-svg-icons";
    import {sendMessage} from "../Stores/AlertStore.js";
    import Fa from "svelte-fa";
    import ScreenshotModal from "./Components/ScreenshotModal.svelte";
    import Cell from "./Components/Cell.svelte";

    let fetching = true;
    export let id = "";
    export let test_id = "";
    let results = [];
    let filters = [];
    let selectedFilters = [];
    let filteredTables = [];
    let selectedScreenshot = "";

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

                    // Escape all '#' characters to prevent issue linking in GitHub
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

    const transformToTable = (tableData) => {
        // Transform table data to a more usable format for rendering: {table_name: {description, table_data, columns, rows}}
        // where table_data: {row_name: {column_name: {value, status, type}}}
        let transformedData = {};

        tableData.forEach((table) => {
            const tableName = table.meta.name;
            const tableDescription = table.meta.description;
            const columnTypesMap = table.meta.columns_meta.reduce((map, colMeta) => {
                map[colMeta.name] = colMeta.type;
                return map;
            }, {});
            const columnNames = table.meta.columns_meta.map(colMeta => colMeta.name);

            transformedData[tableName] = {
                description: tableDescription,
                table_data: {},
                columns: [],
                rows: []
            };

            let presentColumns = new Set();
            let presentRows = new Set();

            // Filter out non-existent rows and columns while keeping order
            table.cells.forEach(cell => {
                presentColumns.add(cell.column);
                presentRows.add(cell.row);
            });

            transformedData[tableName].columns = table.meta.columns_meta.filter(colMeta => presentColumns.has(colMeta.name));
            transformedData[tableName].rows = table.meta.rows_meta.filter(row => presentRows.has(row));

            // building data structure (table_data)
            transformedData[tableName].rows.forEach(row => {
                transformedData[tableName].table_data[row] = {};
            });
            let table_status = "PASS";
            table.cells.forEach(cell => {
                const column = cell.column;
                const row = cell.row;
                const value = cell.value || cell.value_text;
                const status = cell.status;

                // Only add the cell if the column and row are present in the table (in metadata and in cells)
                if (columnNames.includes(column) && transformedData[tableName]["rows"].includes(row)) {
                    transformedData[tableName].table_data[row][column] = {
                        value: value,
                        status: status,
                        type: columnTypesMap[column]
                    };
                }
                if (status !== "UNSET" && status !== "PASS" && table_status !== "ERROR") {
                    table_status = status;
                }
            });
            transformedData[tableName].table_status = table_status;
        });

        console.log(transformedData);
        return transformedData;
    };

    const fetchResults = async function () {
        fetching = true;
        try {
            let apiResponse = await fetch(`/api/v1/run/${test_id}/${id}/fetch_results`);
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                fetching = false;
                results = transformToTable(apiJson.tables);
                extractFilters();
                filterTables();
            }
        } catch (error) {
            console.log(error);
        }
    };

    const extractFilters = () => {
        // Extract filters from the table names by splitting by "-" and grouping by level
        let fltrs = new Map();
        Object.keys(results).forEach(name => {
            const parts = name.split("-");
            parts.forEach((part, index) => {
                const level = index + 1;
                if (!fltrs.has(level)) {
                    fltrs.set(level, new Set());
                }
                fltrs.get(level).add(part.trim());
            });
        });
        filters = Array.from(fltrs.entries()).sort((a, b) => a[0] - b[0]).map(entry => ({
            level: entry[0],
            items: Array.from(entry[1])
        }))
            .filter(entry => entry.items.length > 1);  // Filter out filters with only one item
        filters = filters;
    };

    const toggleFilter = (filterName, level) => {
        // Toggle filter by level - one filter per level can be applied
        const currentFilter = selectedFilters.find(f => f.level === level);
        if (currentFilter && currentFilter.name === filterName) {
            selectedFilters = selectedFilters.filter(f => f.level !== level);
        } else {
            selectedFilters = selectedFilters.filter(f => f.level !== level);
            selectedFilters = [...selectedFilters, {name: filterName, level}];
        }
        filterTables();
    };

    const filterTables = () => {
        // Filter tables by selected filters - only tables that contain all selected filters are shown
        const filteredTableNames = Object.keys(results)
            .filter(title => {
                const parts = title.split("-").map(part => part.trim());
                return selectedFilters.every(filter => parts.includes(filter.name));
            });
        filteredTables = Object.keys(results)
            .filter(key => filteredTableNames.includes(key))
            .reduce((obj, key) => {
                obj[key] = results[key];
                return obj;
            }, {});
    };

    const getFilterColor = (level) => {
        const filterColors = ["#7fbfff", "#ff7f7f", "#ffbf7f", "#bf7fff", "#bf7f7f", "#7fffff", "#ffff7f"];
        return filterColors[(level - 2) % filterColors.length];
    };

    onMount(() => {
        fetchResults();
    });


</script>

<style>
    th, td {
        text-align: center;
    }

    table {
        width: auto;
        table-layout: auto;
    }

    .unit {
        font-size: 0.8em;
        color: gray;
        vertical-align: top;
    }

    /* Custom styles for improved margins and vertical line */
    ul.result-list {
        list-style-type: none;
        padding: 0;
        margin: 0;
    }

    li.result-item {
        margin-bottom: 2rem; /* Space between result tables */
        display: flex;
    }

    li.result-item::before {
        content: "";
        display: block;
        width: 5px;
        background-color: #ddd; /* Color of the vertical line */
        margin-right: 1rem;
        border-radius: 2px;
    }

    li.result-item.PASS::before {
        background-color: var(--bs-success) !important;
    }

    li.result-item.ERROR::before {
        background-color: var(--bs-danger) !important;
    }

    .result-content {
        flex-grow: 1;
    }

    .filters-container {
        display: flex;
        justify-content: flex-start;
        align-items: center;
        margin-bottom: 20px;
        flex-wrap: wrap;
    }

    .filters-container button {
        margin: 5px;
        padding: 10px 15px;
        cursor: pointer;
        border: none;
        border-radius: 5px;
    }

    .filters-container button:hover {
        background-color: #e0e0e0;
    }

    .filters-container button.selected {
        border: 2px solid #333;
    }
</style>

{#if !fetching }
    <div class="p-2">
        <div class="filters-container {Object.keys(filters).length < 2 ? 'd-none' : ''}">
            <button on:click={() => { selectedFilters = []; filterTables();  }}>Show All</button>
            {#each filters as filterGroup}
                {#each filterGroup.items as filter}
                    <button
                            on:click={() => toggleFilter(filter, filterGroup.level)}
                            class:selected={selectedFilters.some(f => f.name === filter)}
                            style="background-color: {getFilterColor(filterGroup.level)}"
                    >
                        {filter}
                    </button>
                {/each}
            {/each}
        </div>
        <ul class="result-list">
            {#each Object.entries(filteredTables) as [table_name, result]}
                <li class="result-item {result.table_status}">
                    <div class="result-content">
                        <h4>{table_name}</h4>
                        <span>{result.description}</span>
                        <table class="table table-bordered">
                            <thead class="thead-dark">
                            <tr>
                                <th>
                                    <button class="btn btn-outline-success" on:click={copyResultTableAsMarkdown}>
                                        <Fa icon={faMarkdown}/>
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
                </li>
            {/each}
        </ul>
    </div>
    <ScreenshotModal bind:selectedScreenshot />
{:else}
    <div class="mb-2 text-center p-2">
        <span class="spinner-border spinner-border-sm"></span> Loading results...
    </div>
{/if}
