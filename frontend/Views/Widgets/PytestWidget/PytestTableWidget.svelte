<script lang="ts">
    import Fuse from "fuse.js";
    import PytestResultRow from "./PytestResultRow.svelte";
    import { PytestResult } from "./ViewPytestOverview.svelte";

    export let testData: PytestResult[];

    let PAGE_SIZE = 3;
    let currentPage = 0;
    let filterString = "";
    const shouldFilter = function (test: PytestResult, filterString: string): boolean {
        if (!filterString) return false;
        if (!test) return true;
        const allTerms = `${test.name}`;
        return allTerms.toLowerCase().search(filterString.toLowerCase()) == -1;
    };

    const paginateTestData = function(testData: PytestResult[], filterString = ""): PytestResult[][] {
        if (testData.length == 0) return [];
        const filtered = testData.filter(v => !shouldFilter(v, filterString));
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

    let pagedTests = paginateTestData(testData, filterString);
    $: pagedTests = paginateTestData(testData, filterString);

</script>

<div class="rounded bg-light-one p-2">
    <div class="rounded bg-white p-2 mb-2">
        <input class="form-control form-input" type="text" placeholder="Name + Userfields filter" bind:value={filterString}>
    </div>
    <div class="rounded bg-white p-2">
        <div>
            {#each pagedTests[currentPage] as item}
                <PytestResultRow test={item} />
            {/each}
        </div>
    </div>
</div>

<div class="d-flex flex-wrap p-2">
    {#each pagedTests as _, idx}
        <button class="btn btn-sm btn-primary me-1 mb-1" on:click={() => currentPage = idx}>{idx + 1}</button>
    {/each}
</div>
