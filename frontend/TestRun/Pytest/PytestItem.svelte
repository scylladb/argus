<script lang="ts">
    import Fa from "svelte-fa";
    import { PytestBgStyles, PytestTextStyles } from "../../Common/TestStatus";
    import {type PytestData, PytestStatus} from "./types";
    import { faChevronDown, faChevronUp, faClipboard, faCopy, faFilter } from "@fortawesome/free-solid-svg-icons";
    import humanizeDuration from "humanize-duration";

    interface Props {
        item: PytestData;
    }

    let { item }: Props = $props();
    type UserFields = Record<string, string>;
    let testExpanded = $state(false);
    let showDetails = $state(false);

    const fetchUserFields = async function(name: string, id: string): Promise<UserFields> {
        try {
            const res = await fetch(`/api/v1/views/widgets/pytest/${name}/${id}/fields`);
            const json = await res.json();

            if (json.status !== "ok") {
                throw json;
            }

            return Promise.resolve(json.response as UserFields);
        } catch (e) {
            console.log("Failed fetching userfields", e);
        }

        return {};
    };

</script>

<div class="mx-1 p-2 bg-light-three border rounded overflow-hidden mb-2">
        <div class="d-flex flex-wrap align-items-center">
        <div class="overflow-hidden test-name">
            {item.name}
        </div>
        <div class="ms-auto rounded px-2 bg-light text-dark">
            {humanizeDuration(item.duration * 1000, {round: true, largest: 2})}
        </div>
        <div class="ms-2 rounded text-light px-2 {PytestTextStyles[item.status]} {PytestBgStyles[item.status]}">
            {item.status}
        </div>
        <div class="ms-2">
            <button class="btn btn-sm btn-primary" onclick={() => { showDetails = !showDetails; testExpanded = true; }}><Fa icon={showDetails ? faChevronUp : faChevronDown}/></button>
        </div>
    </div>
    <div class:show={showDetails} class="rounded overflow-hidden bg-main collapse">
        <div class="mb-2">
            {#each item.markers as marker}
                <div class="btn btn-sm btn-dark me-1">{marker}</div>
            {/each}
        </div>
        {#if item.message}
            <div class="mb-2 bg-white p-1">
                <h6 class="mb-1">Message <button class="btn btn-sm btn-success" onclick={() => navigator.clipboard.writeText(item.message)}><Fa icon={faCopy}/></button></h6>
                <pre class="bg-main code rounded p-2 markdown-body" style="white-space: pre-wrap;">{item.message}</pre>
            </div>
        {/if}
        {#if testExpanded}
            {#await fetchUserFields(item.name, item.id)}
                <div class="text-center p-4 text-muted d-flex align-items-center justify-content-center">
                    <span class="spinner-grow me-2"></span> Loading User Fields...
                </div>
            {:then fields}
                {@const userFields = Object.entries(fields)}
                {#if userFields.length > 0}
                    <table class="table table-responsive table-bordered table-striped table-hover">
                        <thead>
                            <tr>
                                <th>Key</th>
                                <th>Value</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each userFields as [key, value] (key)}
                                <tr>
                                    <td class="key-cell">
                                        <span class="fw-bold">{key}</span>
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
                                            onclick={() => navigator.clipboard.writeText(value)}
                                        >
                                            <Fa icon={faCopy}/>
                                        </button>
                                    </td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                {:else}
                    <div class="text-center p-2 rounded bg-light-two text-muted">No User Fields</div>
                {/if}
            {/await}
        {/if}
    </div>
</div>
