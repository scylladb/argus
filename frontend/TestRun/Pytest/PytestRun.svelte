<script lang="ts">
    import {onDestroy, onMount} from "svelte";
    import {sendMessage} from "../../Stores/AlertStore";
    import PytestItem from "./PytestItem.svelte";
    import {type PytestData, PytestStatus, PytestStatuses} from "./types";
    import IntersectionObserver from "../../Utils/IntersectionObserver.svelte";
    import Fa from "svelte-fa";
    import { faCheck, faTimes } from "@fortawesome/free-solid-svg-icons";
    import { titleCase } from "../../Common/TextUtils";
    import { PytestBtnStyles } from "../../Common/TestStatus";

    interface Props {
        runId: string;
    }

    let { runId }: Props = $props();

    const PAGE_SIZE_STEP = 100;

    let data: PytestData[] | null = $state(null);
    let refreshInterval: any = null;
    let failedToLoad = $state(false);
    let pageSize = $state(PAGE_SIZE_STEP);
    let filters = $state({
        search: "",
        status: {
            [PytestStatus.PASSED]: false,
            [PytestStatus.FAILURE]: true,
            [PytestStatus.ERROR]: true,
            [PytestStatus.XFAILED]: false,
            [PytestStatus.XPASS]: false,
            [PytestStatus.PASSED_ERROR]: true,
            [PytestStatus.FAILURE_ERROR]: true,
            [PytestStatus.SKIPPED_ERROR]: true,
            [PytestStatus.ERROR_ERROR]: true,
            [PytestStatus.SKIPPED]: false,
        },
    });


    let filteredData = $derived(data?.filter((test) => {
        const status = test.status;
        if (filters.search.length === 0) {
            return filters.status[status];
        }

        return filters.status[status] && test.name.toLowerCase().includes(filters.search.toLowerCase());
    }));

    const fetchData = async () => {
        try {
            const response = await fetch(`/api/v1/run/${runId}/pytest/results`);
            const responseData: { status: string, response: PytestData[] } = await response.json();

            if (!response.ok) {
                failedToLoad = true;
                sendMessage(
                    "error",
                    "HTTP Transport Error.",
                    "PytestRun::fetchData"
                );
                console.log(response);
                return null;
            }

            return responseData.response;
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching dtest run data.\nMessage: ${error.response.arguments[0]}`,
                    "PytestRun::fetchData"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during dtest run data fetch",
                    "PytestRun::fetchData"
                );
                console.log(error);
            }
        }

        return null;
    };

    const onStatusFilterChange = (status: PytestStatus) => {
        filters.status[status] = !filters.status[status];
    };

    onMount(async () => {
        data = await fetchData();
        if (data) {
            refreshInterval = setInterval(async () => {
                if (!document.hasFocus()) return;
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
    <div class="container-fluid">
        <div class="row w-100">
            <div class="col p-2">
                <input
                        class="form-control"
                        type="text"
                        placeholder="Filter by string"
                        bind:value="{filters.search}"
                >
            </div>
        </div>
        <div class="row w-100">
            <div class="col">
                <div class="d-flex flex-wrap">
                    {#each PytestStatuses as status}
                        <button class="btn btn-sm {PytestBtnStyles[status]} me-2 mb-2" onclick={() => onStatusFilterChange(status)}>
                            <Fa icon={filters.status[status] ? faCheck : faTimes} /> {titleCase(status)}
                        </button>
                    {/each}
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
            <div class="mb-2">
                <IntersectionObserver  top={20}>
                    {#snippet children({ intersecting })}
                                        {#each filteredData.slice(0, pageSize) as test (`${test.name}-${test.id}`)}
                            {#if intersecting}
                                <PytestItem item={test}/>
                            {/if}
                        {/each}
                                                        {/snippet}
                                </IntersectionObserver>
            </div>
            {#if filteredData.length > PAGE_SIZE_STEP}
                <div>
                    <button class="btn btn-primary w-100" onclick={() => pageSize += PAGE_SIZE_STEP}>Show more</button>
                </div>
            {/if}
        {/if}

    {:else if failedToLoad}
        <div class="text-center p-2 m-1 d-flex align-items-center justify-content-center">
            <span class="fs-4">Run not found.</span>
        </div>
    {:else}
        <div class="text-center p-2 m-1 d-flex align-items-center justify-content-center">
            <span class="spinner-border me-4"></span><span class="fs-4">Loading...</span>
        </div>
    {/if}
</div>
