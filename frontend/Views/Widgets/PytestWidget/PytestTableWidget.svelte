<script lang="ts">
    import { faSearch } from "@fortawesome/free-solid-svg-icons";
    import PytestResultRow from "./PytestResultRow.svelte";
    import type { PytestResult } from "./ViewPytestOverview.svelte";
    import Fa from "svelte-fa";
    import { createEventDispatcher, onMount } from "svelte";

    const dispatch = createEventDispatcher();

    let PAGE_SIZE = 50;
    let currentPage = $state(1);
    interface Props {
        testData?: PytestResult[];
        fetching?: boolean;
        filterString?: string;
        testString?: string;
    }

    let {
        testData = [],
        fetching = false,
        filterString = $bindable(""),
        testString = $bindable("")
    }: Props = $props();
    let dirty = $state(false);
    const shouldFilter = function () {
        dispatch("queryUpdated", { query: filterString} );
        dirty = false;
    };

    const shouldSearch = function () {
        dispatch("testNameUpdated", { test: testString} );
        dirty = false;
    };

    const paginateTestData = function(testData: PytestResult[]): PytestResult[][] {
        if (testData.length == 0) return [];
        const filtered = testData;
        const steps = Math.max(parseInt(`${filtered.length / PAGE_SIZE}`) + 1, 1);
        const pages = Array
            .from({length: steps}, () => [])
            .map((_, pageIdx) => {
                const sliceIdx = pageIdx * PAGE_SIZE;
                const slice = filtered.slice(sliceIdx, PAGE_SIZE + sliceIdx);
                return [...slice];
            });
        return pages;
    };

    const loadMore = function(pages: PytestResult[][], pageCounter: number) {
        if (pages.length == 0) return [];
        let data: PytestResult[] = [];
        Array.from({ length: Math.min(pageCounter, pages.length) }).forEach((_, idx) => {
            data = [...data, ...pages[idx]];
        });
        return data;
    };

    let pagedTests = $derived(paginateTestData(testData));

</script>

<div class="rounded bg-light-one p-2">
    <div class="rounded bg-white p-2 mb-2 input-group">
        <input class="form-control form-input" type="text" placeholder="Filter test by name" bind:value={testString} oninput={() => dirty = true}>
        <button class="btn btn-primary" onclick={shouldSearch} disabled={(testString.length == 0 || fetching) && !dirty}><Fa icon={faSearch}/>Search Specific Test</button>
    </div>
    <div class="rounded bg-white p-2 mb-2 input-group">
        <input class="form-control form-input" type="text" placeholder="Filter test body" bind:value={filterString} oninput={() => dirty = true}>
        <button class="btn btn-primary" onclick={shouldFilter} disabled={(filterString.length == 0 || fetching) && !dirty}><Fa icon={faSearch}/>Search</button>
    </div>
    <div class="rounded bg-white p-2">
        <div class="p-1 rounded bg-light-one">
            {#each loadMore(pagedTests, currentPage) as item}
                <PytestResultRow test={item} on:filterSelect on:markerSelect on:testSelect={(e) => {
                        testString = e.detail;
                        dispatch("testNameUpdated", { test: e.detail } );
                    }}/>
            {:else}
                <div class="p-4 text-muted text-center">
                    No data available.
                </div>
            {/each}
        </div>
    </div>

    {#if pagedTests.length > 1}
        <div class="my-2">
                <button class="w-100 btn btn-primary me-1 mb-1" onclick={() => currentPage += 1}>Show more...</button>
        </div>
    {/if}
</div>
