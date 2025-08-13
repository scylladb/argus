<script module lang="ts">
    import { PytestBtnStyles, PytestColors, PytestStatus } from "../../../Common/TestStatus";
    export interface PytestResult {
        duration: number;
        id: string;
        markers: string[];
        name: string;
        release_id: string;
        run_id: string;
        session_timestamp: string;
        status: typeof PytestStatus[keyof typeof PytestStatus];
        test_id: string;
        message: string;
        test_timestamp: string;
        test_type: string;
        user_fields: Record<string, string>;
    }

    export interface IStatusCount {
        [key: string]: number;
    }

    export interface ITestStats {
        [timestamp: string]: {
            [V in typeof PytestStatus[keyof typeof PytestStatus]]?: number;
        }
    }

    export interface IBarChart {
        labels: string[];
        datasets: {
            label: string;
            data: number[];
        }[];
    }

    interface IWidgetState {
        before: number | null;
        test: string | null;
        after: number | null;
        status: { [V in typeof PytestStatus[keyof typeof PytestStatus]]: boolean },
        query: string | null;
        filters: string[];
        limit: number | null;
        markers: string[];
    }

    interface IStatusFilter {
        [k: string]: boolean;
    }
</script>

<script lang="ts">
    import { run } from 'svelte/legacy';

    import { Chart } from "chart.js";
    import { onMount } from "svelte";
    import { titleCase } from "../../../Common/TextUtils";
    import PytestTableWidget from "./PytestTableWidget.svelte";
    import queryString from "query-string";
    import { faCheck, faCircle, faExclamation, faRefresh, faTimes } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import PytestCalendarSelector from "./PytestCalendarSelector.svelte";
    import dayjs from "dayjs";


    interface Props {
        dashboardObject: Record<string, unknown>;
        /**
     * @type {string}
     */
        dashboardObjectType: string;
        settings: {
        enabledStatuses: string[]
    };
    }

    let { dashboardObject, dashboardObjectType, settings }: Props = $props();

    let pytestBarStatsCanvas: HTMLCanvasElement | null = $state(null);
    let pytestBarChart: Chart<"bar">;
    let pytestPieChartCanvas: HTMLCanvasElement | null = $state(null);
    let pytestPieChart: Chart<"pie">;
    let dirty = $state(false);
    let fetching = $state(false);
    let total = $state(0);

    interface IRoutes {
        [key: string]: string;
    }

    const ROUTES: IRoutes = {
        release: "/api/v1/views/widgets/pytest/release/$id/results",
        view: "/api/v1/views/widgets/pytest/view/$id/results",
    };

    let testData: PytestResult[] = $state([]);

    const defaultAfterDate = function (days = 30) {
        return dayjs().subtract(days, "days").unix();
    };

    const loadStatusState = function(statuses: string[], preset = true): IStatusFilter {
        const statusFilter = Object.values(PytestStatus).reduce((a, s) => {a[s] = preset; return a;}, {} as IStatusFilter);
        statuses.forEach(status => statusFilter[status] = true);
        return statusFilter;
    };

    const loadPytestDashState = function () {
        const qs = queryString.parse(document.location.search, { arrayFormat: "bracket" });
        return {
            before: qs.pytestBefore ? new Number(qs.pytestBefore) : null,
            after: qs.pytestAfter ? new Number(qs.pytestAfter) : defaultAfterDate(),
            status: qs.pytestStatus ? loadStatusState(qs.pytestStatus as string[], false) : loadStatusState(settings.enabledStatuses || [], false),
            query: qs.pytestQuery || null,
            test: qs.pytestTest || null,
            filters: qs.pytestFilters || [],
            limit: qs.pytestLimit || null,
            markers: qs.pytestMarkers || [],
        };
    };


    let widgetState: IWidgetState = $state(loadPytestDashState() as IWidgetState);

    const fetchPytestStats = async function () {
        try {
            fetching = true;
            const qs = {
                before: widgetState.before,
                after: widgetState.after,
                filters: widgetState.filters,
                test: widgetState.test,
                markers: widgetState.markers,
                query: widgetState.query,
                status: Object.keys(widgetState.status).filter(v => widgetState.status[v]),
            };

            const res = await fetch(ROUTES[dashboardObjectType].replace("$id", dashboardObject.id as string) + `?${queryString.stringify(qs, { arrayFormat: "bracket" })}`);
            const json = await res.json();

            if (json.status !== "ok") {
                dirty = true;
                throw json;
            }
            testData = json.response.hits;
            total = json.response.total;
            createBarChar(json.response.barChart);
            createPieChart(json.response.pieChart);
            dirty = false;
        } catch (e) {
            console.log("Failed fetching stats", e);
        } finally {
            fetching = false;
        }
    };

    let statsPromise = fetchPytestStats();

    const forceRefresh = async function () {
        await fetchPytestStats();
    };

    const handleQueryUpdate = function (event: CustomEvent) {
        dirty = true;
        let query = event.detail.query as string;
        widgetState.query = query;
        forceRefresh();
    };

    const handleTestNameUpdate = function (event: CustomEvent) {
        dirty = true;
        let test = event.detail.test as string;
        widgetState.test = test;
        forceRefresh();
    };

    const handleMarkerClick = function(event: CustomEvent) {
        let marker = event.detail.marker as string;
        if (widgetState.markers.includes(marker)) return;
        dirty = true;
        widgetState.markers.push(marker);
        widgetState.markers = widgetState.markers;
    };

    const createPieChart = function (counts: IStatusCount) {
        if (pytestPieChart) {
            pytestPieChart.destroy();
        }

        if (!pytestPieChartCanvas) return;

        pytestPieChart = new Chart(pytestPieChartCanvas, {
            type: "pie",
            data: {
                labels: Object.keys(counts),
                datasets: [
                    {
                        data: Object.values(counts),
                        backgroundColor: Object.keys(counts).map((k) => PytestColors[k as keyof typeof PytestColors] || PytestColors.skipped),
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: false,
                    },
                },
            },
        });
    };

    const createBarChar = function (barChart: IBarChart) {
        if (pytestBarChart) {
            pytestBarChart.destroy();
        }

        if (!pytestBarStatsCanvas) return;

        pytestBarChart = new Chart(pytestBarStatsCanvas, {
            type: "bar",
            data: {
                labels: barChart.labels,
                datasets: barChart.datasets.map(set => ({ ...set, backgroundColor: PytestColors[set.label] })),
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        display: false,
                    },
                    title: {
                        display: true,
                        text: "Overview",
                    },
                    tooltip: {
                        mode: "index",
                        intersect: false,
                        position: "nearest",
                        callbacks: {
                            title: (tooltipItems) => {
                                return tooltipItems[0].label;
                            },
                            label: (context) => {
                                const label = context.dataset.label;
                                const value = context.parsed.y;
                                return `${label}: ${value}`;
                            },
                        },
                    },
                },
                interaction: {
                    mode: "index",
                    intersect: true,
                    axis: "x",
                },
                onHover: (event, chartElements) => {
                    if (!event?.native?.target) return;
                    const canvas = event.native.target as HTMLCanvasElement;
                    canvas.style.cursor = chartElements.length > 0 ? "pointer" : "default";
                },
                scales: {
                    x: {
                        stacked: true,
                    },
                    y: {
                        stacked: true,
                    },
                },
                onClick: () => {
                    // empty
                },
            },
        });
    };

    const parseFilter = function (filter: string): [string, string, boolean] {
        const rawFilter = filter.replace(/!/, "");
        const [key, value] = rawFilter.split("=", 2);
        console.log(key, value, rawFilter);
        return [key, value, filter[0] == "!"];
    };

    const alterFilter = function(filter: string) {
        const idx = widgetState.filters.findIndex(v => v == filter);
        widgetState.filters[idx] = filter[0] == "!" ? filter.replace(/!/, "") : `!${filter}`;
        dirty = true;
    };

    const handleFilterClick = function (event: CustomEvent) {
        const filter = event.detail.filter as string;
        const value = event.detail.value as string;
        const rawFilter = `${filter}=${value}`;
        if (widgetState.filters.includes(rawFilter)) return;
        widgetState.filters.push(rawFilter);
        widgetState = widgetState;
        dirty = true;
    };

    run(() => {
        const qs = queryString.parse(document.location.search, { arrayFormat: "bracket" });
        const newQs = {
            ...qs,
            pytestBefore: widgetState.before ?? undefined,
            pytestAfter: widgetState.after ?? undefined,
            pytestStatus: Object.entries(widgetState.status).filter(([_, state]) => state).map(([status, _]) => status),
            pytestQuery: widgetState.query ?? undefined,
            pytestFilters: widgetState.filters.length ? widgetState.filters : undefined,
            pytestLimit: widgetState.limit ?? undefined,
            pytestMarkers: widgetState.markers.length ? widgetState.markers : undefined,
            pytestTest: widgetState.test ? widgetState.test : undefined,
        };
        const search = queryString.stringify(newQs, { arrayFormat: "bracket" });
        window.history.pushState(null, "", `?${search}`);
    });

    onMount(async () => {
        //empty
    });
</script>

<div>
    {#await statsPromise}
        <div class="text-center p-4 text-muted d-flex align-items-center justify-content-center">
            <span class="spinner-grow me-2"></span> Loading Test Results...
        </div>
    {:then value}
        <div class="d-flex">
            <div class="">
                <h5>Status</h5>
                <div class="p-1 d-flex flex-wrap w-50">
                    {#each Object.entries(widgetState.status) as [status, state]}
                        <button
                            class="mb-2 ms-2 btn btn-sm {PytestBtnStyles[status] || PytestBtnStyles.skipped}"
                            onclick={() => {widgetState.status[status] = !state; dirty = true;}}
                        >
                            <Fa icon={widgetState.status[status] ? faCheck : faTimes}/>
                            {status.split(" ").map(v => titleCase(v)).join(" ")}
                        </button>
                    {/each}
                </div>
            </div>
            <div class="ms-auto p-2">
                <PytestCalendarSelector bind:before={widgetState.before} bind:after={widgetState.after} on:setDirty={() => (dirty = true)}/>
                {#if dirty}
                    <div class="text-end">
                        <button class="btn btn-primary" onclick={forceRefresh} disabled={fetching}><span class:fetching><Fa icon={faRefresh}/></span> Refresh</button>
                    </div>
                {/if}
            </div>
        </div>
    {/await}
    <div class="d-flex p-2">
        <div class="w-25">
            <canvas bind:this={pytestPieChartCanvas}></canvas>
        </div>
        <div class="ms-2 w-75">
            <canvas bind:this={pytestBarStatsCanvas}></canvas>
        </div>
    </div>
    <div>
        {#if widgetState.markers.length > 0}
        <div class="bg-light-one rounded p-2">
            <div class="bg-white rounded p-2">
                <div>Markers</div>
                <div class="bg-light-one p-1 d-flex flex-wrap rounded">
                    {#each widgetState.markers as marker}
                        <div class="btn-group me-1 mb-1">
                            <button class="btn btn-sm btn-dark">
                                {marker}
                            </button>
                            <button class="btn btn-sm btn-dark" onclick={() => {
                                widgetState.markers = widgetState.markers.filter(m => m != marker);
                                dirty = true;
                            }}>
                                <Fa icon={faTimes}/>
                            </button>
                        </div>
                    {/each}
                </div>
            </div>
        </div>
        {/if}
    </div>
    <div>
        {#if widgetState.filters.length > 0}
            <div class="bg-light-one rounded p-2">
                <div class="bg-white rounded p-2">
                    <div>User Fields</div>
                    <div class="bg-light-one p-1 d-flex flex-wrap rounded">
                        {#each widgetState.filters as filter}
                            {@const [filterName, filterValue, negated] = parseFilter(filter)}
                            <div class="btn-group me-1 mb-1">
                                <button class="btn btn-sm btn-dark" onclick={() => alterFilter(filter)}>
                                    {#if negated}
                                        <Fa icon={faExclamation}/>
                                    {:else}
                                        <Fa icon={faCircle} />
                                    {/if}
                                </button>
                                <button class="btn btn-sm btn-dark">
                                    {filterName} = {filterValue}
                                </button>
                                <button class="btn btn-sm btn-dark" onclick={() => {
                                    widgetState.filters = widgetState.filters.filter(m => m != filter);
                                    dirty = true;
                                }}>
                                    <Fa icon={faTimes}/>
                                </button>
                            </div>
                        {/each}
                    </div>
                </div>
            </div>
        {/if}
    </div>
    <div class="text-muted text-end p-2">
        Total {total} tests. (Last 500 are shown)
    </div>
    <div class="w-100">
        <PytestTableWidget {testData} {fetching} testString={widgetState.test || ""} filterString={widgetState.query || ""} on:testNameUpdated={handleTestNameUpdate} on:queryUpdated={handleQueryUpdate} on:markerSelect={handleMarkerClick} on:filterSelect={handleFilterClick}/>
    </div>
</div>


<style>
    .fetching {
        animation: rotating 2s linear infinite;
        display: inline-block;
    }
    @keyframes rotating {
        to { transform: rotate(360deg); }
    }
</style>
