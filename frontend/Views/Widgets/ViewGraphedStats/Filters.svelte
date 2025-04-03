<script lang="ts">
    import { derived } from "svelte/store";
    import type { DataResponse } from "./Interfaces";

    export let allData: DataResponse;
    export let selectedFilter: string;
    export let onFilterChange: (filter: string) => void;

    const versions = derived(
        { subscribe: (fn) => () => {} }, // Dummy store for derived since allData is a prop
        () => [...new Set(allData.test_runs.map((run) => run.version))].sort()
    );
    const releases = derived(versions, ($versions) =>
        [...new Set($versions.map((v) => v.split(".").slice(0, 2).join(".")))].sort()
    );
</script>

<div class="mb-4">
    <div class="btn-group mb-3" role="group">
        <button
            class:active={selectedFilter === ""}
            class="btn btn-outline-secondary"
            on:click={() => onFilterChange("")}>All</button
        >
        {#each $releases as release}
            <button
                class:active={selectedFilter === release}
                class="btn btn-outline-secondary"
                on:click={() => onFilterChange(release)}>{release}</button
            >
        {/each}
    </div>
    <div class="btn-group mb-3" role="group">
        {#each $versions as version}
            <button
                class:active={selectedFilter === version}
                class="btn btn-outline-primary btn-sm"
                on:click={() => onFilterChange(version)}>{version}</button
            >
        {/each}
    </div>
    <button class="btn btn-sm btn-outline-secondary ms-2" on:click={() => onFilterChange("")}> Reset Filters </button>
</div>
