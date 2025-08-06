<script lang="ts">
    import { run } from 'svelte/legacy';

    import dayjs from "dayjs";
    import {createEventDispatcher, onMount} from "svelte";

    interface Props {
        dateRange?: number;
        releasesFilters?: any;
    }

    let { dateRange = $bindable(6), releasesFilters = $bindable({}) }: Props = $props();

    let showCustomInputs = $state(false);
    let startDate = $state("");
    let endDate = $state("");

    const dispatch = createEventDispatcher();

    const setDateRange = (months) => {
        if (months === -1) {
            showCustomInputs = true;
            return;
        }
        const now = dayjs();
        endDate = now.format('YYYY-MM-DD');
        const pastDate = now.subtract(months, 'month');
        startDate = pastDate.format('YYYY-MM-DD');
        showCustomInputs = false;
        dispatch('dateChange', { startDate, endDate });
    };

    const toggleReleaseFilter = (release) => {
        releasesFilters[release] = !releasesFilters[release];
        dispatch('releaseChange', { releasesFilters });
    };

    onMount(() => {
        setDateRange(dateRange);
    });

    run(() => {
        setDateRange(dateRange);
    });
</script>

<div class="filters-container">
    <span class="my-auto">Time range:</span>
    <div class="input-group input-group-inline input-group-sm mx-2">
        <button class="btn btn-outline-primary btn-sm"
                class:active={dateRange === 1}
                onclick={() => dateRange = 1}>
            Last Month
        </button>
        <button class="btn btn-outline-primary btn-sm"
                class:active={dateRange === 3}
                onclick={() => dateRange = 3}>
            Last 3 Months
        </button>
        <button class="btn btn-outline-primary btn-sm"
                class:active={dateRange === 6}
                onclick={() => dateRange = 6}>
            Last 6 Months
        </button>
        <button class="btn btn-outline-primary btn-sm"
                class:active={dateRange === 12}
                onclick={() => dateRange = 12}>
            Last year
        </button>
        <button class="btn btn-outline-primary btn-sm"
                class:active={dateRange === 24}
                onclick={() => dateRange = 24}>
            Last 2 years
        </button>
        <button class="btn btn-outline-primary btn-sm"
                onclick={() => dateRange = -1}
                class:active={showCustomInputs}>
            Custom
        </button>
        {#if showCustomInputs}
            <input type="date" class="form-control date-input" bind:value={startDate} onchange={() => dispatch('dateChange', { startDate, endDate })}/>
            <input type="date" class="form-control date-input" bind:value={endDate} onchange={() => dispatch('dateChange', { startDate, endDate })}/>
        {/if}
    </div>
    <span class="my-auto">Releases:</span>
    <div class="input-group input-group-inline input-group-sm mx-2">
        {#each Object.keys(releasesFilters) as release}
            <button class="btn btn-sm btn-outline-dark"
                    onclick={() => toggleReleaseFilter(release)}
                    class:active={releasesFilters[release]}
            >
                {release}
            </button>
        {/each}
    </div>
</div>

<style>
    .filters-container {
        display: flex;
        flex-wrap: nowrap;
        align-items: center;
        margin: 10px 0;
        gap: 10px;
    }

    .date-input {
        width: 150px;
    }

    .input-group {
        flex-wrap: nowrap;
    }
</style>
