<script>
    import {onMount} from "svelte";
    import {ResultCellStatusStyleMap} from "../Common/TestStatus";

    let fetching = true;
    export let id = "";
    export let test_id = "";
    let results = [];

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

            table.cells.forEach(cell => {
                const column = cell.column;
                const row = cell.row;
                const value = cell.value;
                const status = cell.status;

                // Only add the cell if the column and row are present in the table (in metadata and in cells)
                if (columnNames.includes(column) && transformedData[tableName]["rows"].includes(row)) {
                    transformedData[tableName].table_data[row][column] = {
                        value: value,
                        status: status,
                        type: columnTypesMap[column]
                    };
                }
            });
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
            }
        } catch (error) {
            console.log(error);
        }
    };

    const durationToStr = (seconds) => {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${secs.toString().padStart(2, '0')}`;
    };

    const formatValue = (value, type) => {
        switch (type) {
        case "FLOAT":
            return value.toFixed(2);
        case "INTEGER":
            return value.toLocaleString();
        case "DURATION":
            return durationToStr(value);
        default:
            return value;
        }
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
</style>

{#if !fetching}
    <div class="p-2">
        {#each Object.entries(results) as [table_name, result]}
            <div class="">
                <h3>{table_name}</h3>
                <span>{result.description}</span>
                <table class="table table-bordered">
                    <thead class="thead-dark">
                    <tr>
                        <th></th>
                        {#each result.columns as col}
                            <th>{col.name} <span class="unit">[{col.unit}]</span></th>
                        {/each}
                    </tr>
                    </thead>
                    <tbody>
                    {#each result.rows as row}
                        <tr>
                            <td>{row}</td>
                            {#each result.columns as col}
                                <td class="{ResultCellStatusStyleMap[result.table_data[row][col.name]?.status || 'NULL']}">
                                    {formatValue(result.table_data[row][col.name]?.value || "", result.table_data[row][col.name]?.type || "NULL")}
                                </td>
                            {/each}
                        </tr>
                    {/each}
                    </tbody>
                </table>
            </div>
        {:else}
            <div class="row">
                <div class="col text-center p-1 text-muted">No results for this run.</div>
            </div>
        {/each}
    </div>
{:else}
    <div class="mb-2 text-center p-2">
        <span class="spinner-border spinner-border-sm"></span> Loading results...
    </div>
{/if}

