<script lang="ts">
    import Fa from "svelte-fa";
    import { PytestResult } from "./ViewPytestOverview.svelte";
    import { faChevronDown, faChevronUp, faClipboard, faCopy, faFilter } from "@fortawesome/free-solid-svg-icons";
    import { PytestBgStyles, PytestTextStyles } from "../../../Common/TestStatus";
    import humanizeDuration from "humanize-duration";
    import { timestampToISODate } from "../../../Common/DateUtils";
    import { createEventDispatcher } from "svelte";

    export let test: PytestResult;

    const dispatch = createEventDispatcher();

    let showDetails = false;
</script>

<div class="p-1 bg-white rounded mb-2 p-2">
    <div class="d-flex flex-wrap align-items-center">
        <div class="overflow-hidden">
            {test.name}
        </div>
        <div class="ms-auto rounded px-2 bg-light text-dark">
            {humanizeDuration(test.duration, {round: true, largest: 2})}
        </div>
        <div class="ms-2 rounded px-2 bg-primary text-light">
            {timestampToISODate(test.session_timestamp)}
        </div>
        <div class="ms-2 rounded px-2 bg-secondary text-light">
            {timestampToISODate(test.test_timestamp)}
        </div>
        <div class="ms-2 rounded px-2 bg-dark text-light">
            {test.test_type}
        </div>
        <div class="ms-2">
            <a class="bg-primary px-2 d-inline-block rounded text-light" href="/tests/generic/{test.run_id}"><Fa icon={faClipboard}/> Run</a>
        </div>
        <div class="ms-2 rounded text-light px-2 {PytestTextStyles[test.status]} {PytestBgStyles[test.status]}">
            {test.status}
        </div>
        <div class="ms-2">
            <button class="btn btn-sm btn-primary" on:click={() => showDetails = !showDetails}><Fa icon={showDetails ? faChevronUp : faChevronDown}/></button>
        </div>
    </div>
    <div class="mb-2">
        {#each test.markers as marker}
            <button class="btn btn-sm btn-dark me-1" on:click={() => dispatch("markerSelect", { marker: marker })}>{marker}</button>
        {/each}
    </div>
    <div class:show={showDetails} class="rounded overflow-hidden bg-main collapse">
        {#if test.user_fields.failure_message || test.message}
            <div class="mb-2 bg-white p-1">
                <h6 class="mb-1">Message <button class="btn btn-sm btn-success" on:click={() => navigator.clipboard.writeText(test.user_fields.failure_message || test.message)}><Fa icon={faCopy}/></button></h6>
                <pre class="bg-main code rounded p-2 markdown-body" style="white-space: pre-wrap;">{test.user_fields.failure_message || test.message}</pre>
            </div>
        {/if}
        <table class="table table-responsive table-bordered table-striped table-hover">
        <thead>
            <th>Key</th>
            <th>Value</th>
        </thead>
        <tbody>
            {#each Object.entries(test.user_fields) as [key, value] (key)}
                <tr>
                    <td class="key-cell">
                        <span class="fw-bold">{key}</span>
                        <button class="btn btn-sm btn-dark d-none" on:click={() => dispatch("filterSelect", { filter: key })}>
                            <Fa icon={faFilter} />
                        </button>
                    </td>
                    <td class="user-select-all value-cell">
                        {#if value.startsWith("http")}
                            <a href="{value}">{value}</a>
                        {:else if value.search(/^<a.*>/) != -1}
                            {@html value}
                        {:else}
                            {value}
                        {/if}
                        <button
                            class="btn btn-sm btn-dark d-none"
                            on:click={() => navigator.clipboard.writeText(value)}
                        >
                            <Fa icon={faCopy}/>
                        </button>
                    </td>
                </tr>
            {/each}
        </tbody>
    </table>
    </div>
</div>


<style>
    td.key-cell:hover button {
        display: inline !important;
    }

    td.value-cell:hover button {
        display: inline !important;
    }
</style>
