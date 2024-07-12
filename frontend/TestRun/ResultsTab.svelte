<script>
    import {onMount} from "svelte";

    let fetching = true;
    export let id = "";
    export let test_id = "";
    let results = [];


    const fetchResults = async function () {
        fetching = true;
        try {
            let apiResponse = await fetch(`/api/v1/run/${test_id}/${id}/fetch_results`);
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {

                fetching = false;
                results = apiJson.tables;
                console.log(results);
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

    const getColumnType = (result, columnName) => {
        return result.meta.columns_meta.find((col) => col.name === columnName).type;
    };

    onMount(() => {
        fetchResults();
    });

    const styleMap = {
        "PASS": "table-success",
        "ERROR": "table-danger",
        "WARNING": "table-warning"
    };

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
        {#each results as result}
            <div class="">
                <h3>{result.meta.name}</h3>
                <span>{result.meta.description}</span>
                <table class="table table-bordered">
                    <thead class="thead-dark">
                    <tr>
                        <th></th>
                        {#each result.meta.columns_meta as col}
                            <th>{col.name} <span class="unit">[{col.unit}]</span></th>
                        {/each}
                    </tr>
                    </thead>
                    <tbody>
                    {#each result.meta.rows_meta as row}
                        <tr>
                            <td>{row}</td>
                            {#each result.meta.columns_meta as col}
                                {#each result.cells as cell}
                                    {#if cell.column === col.name && cell.row === row}
                                        <td class="{styleMap[cell.status]}">{formatValue(cell.value, getColumnType(result, cell.column))}</td>
                                    {/if}
                                {/each}
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

