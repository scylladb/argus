<script lang="ts">
    import {onDestroy, onMount} from "svelte";
    import {sendMessage} from "../../Stores/AlertStore";
    import PytestItem from "./PytestItem.svelte";
    import {type PytestData, PytestStatus, PytestStatuses} from "./types";
    import IntersectionObserver from "../../Utils/IntersectionObserver.svelte";

    export let runId: string;

    const PAGE_SIZE_STEP = 100;

    let data: PytestData[] | null = null;
    let refreshInterval: any = null;
    let failedToLoad = false;
    let pageSize = PAGE_SIZE_STEP;
    let filters = {
        search: "",
        status: {
            [PytestStatus.ERROR]: true,
            [PytestStatus.FAILURE]: true,
            [PytestStatus.XFAILED]: true,
            [PytestStatus.PASSED]: true,
            [PytestStatus.SKIPPED]: true,
            [PytestStatus.XPASS]: true,
            [PytestStatus.PASSED_ERROR]: true,
            [PytestStatus.FAILURE_ERROR]: true,
            [PytestStatus.SKIPPED_ERROR]: true,
            [PytestStatus.ERROR_ERROR]: true,
        },
    };

    $: filteredData = data?.filter((test) => {
        const status = test.status;
        if (filters.search.length === 0) {
            return filters.status[status];
        }

        return filters.status[status] && test.name.toLowerCase().includes(filters.search.toLowerCase());
    });

    const fetchData = async () => {
        try {
            const response = await fetch(`/api/v1/run/${runId}/pytest/results`);
            const responseData: { status: string, response: PytestData[] } = await response.json();

            if (!response.ok) {
                failedToLoad = true;
                sendMessage(
                    "error",
                    "API Error when fetching test run data.",
                    "DriverMatrixTestRun::fetchTestRunData"
                );
                return null;
            }

            return responseData.response;
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching test run data.\nMessage: ${error.response.arguments[0]}`,
                    "DriverMatrixTestRun::fetchTestRunData"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test run data fetch",
                    "DriverMatrixTestRun::fetchTestRunData"
                );
            }
        }

        return null;
    };

    const onStatusFilterChange = (ev: any, status: PytestStatus) => {
        filters.status[status] = ev.target.checked;
    };

    onMount(async () => {
        data = await fetchData();
        if (data) {
            refreshInterval = setInterval(async () => {
                const newData = await fetchData();
                if (newData) {
                    data = newData;
                }
            }, 5000);
        }
    });

    onDestroy(() => {
        if (refreshInterval) {
            clearInterval(refreshInterval);
        }
    });

</script>
<div style="min-height: 24rem; max-height: 48vh; overflow-y: scroll; overflow-x: hidden" class="position-relative">
    <div class="d-flex align-items-end align-center justify-content-end w-100 py-3 position-sticky top-0 bg-white" style="z-index: 1">
        <div class="row w-100">
            <div class="col">
                <input
                        class="form-control"
                        type="text"
                        placeholder="Search test"
                        bind:value="{filters.search}"
                >
            </div>
            <div class="col">
                <div class="btn-group">
                    <button type="button" class="btn btn-info dropdown-toggle" data-bs-toggle="dropdown"
                            aria-expanded="false">
                        Filter Tests
                    </button>
                    <ul class="dropdown-menu">
                        {#each PytestStatuses as status}
                            <li class="dropdown-item">
                                <input
                                        class="form-check-input"
                                        type="checkbox"
                                        id="{status}-checkbox"
                                        checked="{filters.status[status]}"
                                        on:change={(event) => onStatusFilterChange(event, status)}
                                >
                                <label for="{status}-checkbox">{status}</label>
                            </li>
                        {/each}
                    </ul>
                </div>
            </div>
        </div>
    </div>


    {#if filteredData}
        {#if filteredData?.length === 0}
            <div class="text-center p-2 m-1 d-flex align-items-center justify-content-center">
                <span class="fs-4">No tests to display</span>
            </div>
        {:else}
            <div class="accordion accordion-flush mb-2">
                <IntersectionObserver let:intersecting top={20}>
                    {#each filteredData.slice(0, pageSize) as test, idx}
                        {#if intersecting}
                            <PytestItem
                                    testId={test.run_id}
                                    idx={idx}
                                    item={test}
                            />
                        {/if}
                    {/each}
                </IntersectionObserver>
            </div>
            {#if filteredData.length > PAGE_SIZE_STEP}
                <div>
                    <button class="btn btn-primary w-100" on:click={() => pageSize += PAGE_SIZE_STEP}>Show more</button>
                </div>
            {/if}
        {/if}

    {:else if failedToLoad}
        <div class="text-center p-2 m-1 d-flex align-items-center justify-content-center">
            <span class="fs-4">Run not found.</span>
        </div>
    {:else}
        <div class="text-center p-2 m-1 d-flex align-items-center justify-content-center">
            <span class="spinner-border me-4"/><span class="fs-4">Loading...</span>
        </div>
    {/if}
</div>
