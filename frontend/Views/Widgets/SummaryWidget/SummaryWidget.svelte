<script lang="ts">
    import { run } from 'svelte/legacy';

    import {onMount} from "svelte";
    import Fa from 'svelte-fa';
    import Select from "svelte-select";
    import {
        faChevronLeft,
        faChevronRight,
        faChevronDown,
        faChevronUp,
        faExclamationTriangle,
        faExclamationCircle,
        faTimesCircle,
        faCheckCircle,
        faMinusCircle,
        faCircle,
        faSpinner,
        faBan,
    } from '@fortawesome/free-solid-svg-icons';
    import ResultTable from "../../../TestRun/Components/ResultTable.svelte";
    import RunIssues from "./RunIssues.svelte";

    let { dashboardObject } = $props();

    let versions = $state([]);
    let versioned_runs = {};
    let test_info = {};
    let selectedVersionTestInfo = $state({});
    let currentVersionIndex = $state(0);
    let runResults = $state({});
    let selectedScreenshot = $state("");
    let expandedTests = $state({});
    let currentVersionRuns = $state({});
    let filters = $state({});
    let selectedFilters = $state({});
    let filteredTables = $state({});
    let showFilters = $state({});
    let versionItems = $state([]);
    let selectedVersionItem = $state({});
    type TestInfo = {
        build_id: string;
        name: string | null;
    };


    onMount(async () => {
        await fetchResults();
    });

    /**
     * Assigns a name to each test if it is null and sorts the test info by test name.
     *
     * @param data - The test info data to process and sort.
     * @returns The processed and sorted test info data.
     */
    function assignAndSortTestInfo(data: Record<string, TestInfo>): Record<string, TestInfo> {

        Object.entries(data).forEach(([key, value]) => {
            if (value.name === null) {
                const parts = value.build_id.split("/");
                value.name = parts[parts.length - 1];
            }
        });

        const sortedEntries = Object.entries(data).sort(([, a], [, b]) => {
            if (a.name && b.name) {
                return a.name.localeCompare(b.name);
            }
            return 0;
        });

        return Object.fromEntries(sortedEntries);
    }

    async function fetchResults() {
        const response = await fetch(`/api/v1/views/widgets/summary/versioned_runs?view_id=${dashboardObject.id}`);
        const responseJson = await response.json();
        versioned_runs = responseJson.response.versions;
        test_info = assignAndSortTestInfo(responseJson.response.test_info);
        versions = Object.keys(versioned_runs);
        versionItems = versions.map((version, index) => ({
            value: index,
            label: formatVersion(version)
        }));
        selectedVersionItem = versionItems[versions.length - 1];
        await fetchRunResults(versions.length - 1);
    }

    async function fetchRunResults(currentVersionIndex = 0) {
        currentVersionRuns = versioned_runs[versions[currentVersionIndex]];
        selectedVersionTestInfo = {...test_info};
        const runs_response = await fetch(`/api/v1/views/widgets/summary/runs_results`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(currentVersionRuns)
        });
        const responseJson = await runs_response.json();
        runResults = responseJson.response;
        Object.keys(selectedVersionTestInfo).forEach(testId => {
            if (!runResults[testId]) {
                runResults[testId] = {notRun: true};
            }
        });
        expandedTests = Object.fromEntries(Object.keys(runResults).map(testId => [testId, false]));
        Object.keys(currentVersionRuns).forEach(testId => {
            const testData = currentVersionRuns[testId];
            let hasFailedStatus = false;
            Object.values(testData).forEach(runObj => {
                if (runObj.status !== 'passed') {
                    hasFailedStatus = true;
                }
            });
            if (hasFailedStatus) {
                expandedTests[testId] = true;
                if (runResults[testId]) {
                    runResults[testId].hasFailedStatus = true;
                } else {
                    runResults[testId] = {hasFailedStatus: true};
                }
            }
        });
        runResults = Object.fromEntries(
            Object.keys(selectedVersionTestInfo).map(testId => [testId, runResults[testId] || {notRun: true}])
        );
        extractFiltersPerTest();
    }

    function extractFiltersPerTest() {
        Object.keys(runResults).forEach(testId => {
            filters[testId] = [];
            showFilters[testId] = false;
            const fltrs = new Map();

            const testData = runResults[testId];
            if (!testData.notRun) {
                const tableNames = [];
                selectedFilters[testId] = [];
                Object.values(testData).forEach(methodData => {
                    if (methodData && typeof methodData === 'object') {
                        Object.values(methodData).forEach(resultsArray => {
                            if (Array.isArray(resultsArray)) {
                                resultsArray.forEach(tableEntry => {
                                    Object.keys(tableEntry).forEach(table_name => {
                                        tableNames.push({
                                            name: table_name,
                                            status: tableEntry[table_name].table_status
                                        });
                                    });
                                });
                            }
                        });
                    }
                });

                tableNames.forEach(name => {
                    const parts = name.name.split("-");
                    parts.forEach((part, index) => {
                        const level = index + 1;
                        if (!fltrs.has(level)) {
                            fltrs.set(level, new Set());
                        }
                        fltrs.get(level).add(part.trim());
                        if (name.status !== 'PASS' && level < 3) {
                            selectedFilters[testId].push({
                                name: part.trim(),
                                level: level
                            });
                        }
                    });
                });

                filters[testId] = Array.from(fltrs.entries())
                    .sort(([left], [right]) => left - right)
                    .map(([level, items]) => ({
                        level,
                        items: Array.from(items)
                    }))
                    .filter(entry => entry.items.length > 1);

                showFilters[testId] = filters[testId].some(entry => entry.items.length >= 2);
                selectedFilters[testId] = [...selectedFilters[testId]];
                const maxLevel = Math.max(...selectedFilters[testId].map(f => f.level));
                selectedFilters[testId] = selectedFilters[testId].filter(f => f.level === maxLevel);
            }
        });
        filterTablesPerTest();
    }

    function toggleFilter(testId, filterName, level) {
        const currentFilter = selectedFilters[testId].find(f => f.level === level && f.name === filterName);
        if (currentFilter) {
            selectedFilters[testId] = selectedFilters[testId].filter(f => !(f.level === level && f.name === filterName));
        } else {
            selectedFilters[testId] = [...selectedFilters[testId], {name: filterName, level}];
        }
        filterTablesPerTest();
    }

    function filterTablesPerTest() {
        Object.keys(runResults).forEach(testId => {
            const testData = runResults[testId];
            filteredTables[testId] = {};
            if (!testData.notRun) {
                Object.entries(testData).forEach(([methodName, methodData]) => {
                    if (methodName !== 'hasFailedStatus') {
                        filteredTables[testId][methodName] = {};
                        Object.entries(methodData).forEach(([runId, resultsArray]) => {
                            const filteredResultsArray = [];

                            resultsArray.forEach(tableEntry => {
                                const filteredTableEntry = {};

                                Object.entries(tableEntry).forEach(([table_name, result]) => {
                                    const parts = table_name.split("-").map(part => part.trim());
                                    const include = selectedFilters[testId].some(filter => parts.includes(filter.name));

                                    if (include || selectedFilters[testId].length === 0) {
                                        filteredTableEntry[table_name] = result;
                                    }
                                });

                                if (Object.keys(filteredTableEntry).length > 0) {
                                    filteredResultsArray.push(filteredTableEntry);
                                }
                            });

                            filteredTables[testId][methodName][runId] = filteredResultsArray;
                        });
                    }
                });
            }
        });
    }


    function getFilterColor(level) {
        const filterColors = ["#7fbfff", "#ff7f7f", "#ffbf7f", "#bf7fff", "#bf7f7f", "#7fffff", "#ffff7f"];
        return filterColors[(level - 2) % filterColors.length];
    }


    function formatVersion(version) {
        const parts = version.split('-');
        return `${parts[0]} (${parts[1]}) - ${parts[2]}`;
    }

    function toggleTest(testId) {
        expandedTests[testId] = !expandedTests[testId];
        expandedTests = {...expandedTests};
    }
    run(() => {
        currentVersionIndex = selectedVersionItem.value;
    });
    run(() => {
        if (versions.length > 0) fetchRunResults(currentVersionIndex);
    });
</script>

<div class="card shadow-sm">
    {#if versions.length === 0}
        <div class="card-body">
            <div class="alert alert-info">
                <Fa icon={faExclamationTriangle} class="me-2"/>
                No test results available
            </div>
        </div>
    {:else}
        <div class="card-header bg-primary">
            <div class="d-flex justify-content-between align-items-center">
                <h3 class="mb-0 text-white">Test Results Summary</h3>
                <div class="d-flex align-items-center">
                    <button class="btn btn-outline-light me-2"
                            onclick={() => selectedVersionItem = versionItems[currentVersionIndex-1]}
                            disabled={currentVersionIndex === 0}>
                        <Fa icon={faChevronLeft}/>
                    </button>
                    <div style="width: 380px">
                        <Select bind:value={selectedVersionItem} items={versionItems} clearable={false}/>
                    </div>
                    <button class="btn btn-outline-light ms-2"
                            onclick={() => selectedVersionItem = versionItems[currentVersionIndex+1]}
                            disabled={currentVersionIndex === versions.length - 1}>
                        <Fa icon={faChevronRight}/>
                    </button>
                </div>
            </div>
        </div>
        <div class="card-body">
            {#each Object.entries(runResults) as [testId, testData]}
                <div class="mb-4 p-3 border rounded {testData.notRun ? 'border-warning' : testData.hasFailedStatus ? 'border-danger' : 'border-success'}">
                    <h4 class="d-flex justify-content-between align-items-center">
                        <span class={testData.notRun ? 'text-warning' : testData.hasFailedStatus ? 'text-danger' : 'text-success'}>
                            {selectedVersionTestInfo[testId]?.name || testId}
                            {#if testData.notRun}
                                <Fa icon={faMinusCircle} class="text-secondary ms-2"/>
                            {:else if testData.hasFailedStatus}
                                <Fa icon={faTimesCircle} class="text-danger ms-2"/>
                            {:else}
                                <Fa icon={faCheckCircle} class="text-success ms-2"/>
                            {/if}
                        </span>
                        <button class="btn btn-outline-secondary" onclick={() => toggleTest(testId)}>
                            <Fa icon={expandedTests[testId] ? faChevronUp : faChevronDown}/>
                        </button>
                    </h4>
                    {#if expandedTests[testId]}
                        {#if showFilters[testId]}
                            <div class="filters-container">
                                <button class="btn btn-outline-dark colored"
                                        onclick={() => { selectedFilters[testId] = []; filterTablesPerTest(); }}>X
                                </button>
                                {#each filters[testId] as filterGroup}
                                    {#each filterGroup.items as filter}
                                        <button
                                                class="btn btn-outline-dark colored"
                                                onclick={() => toggleFilter(testId, filter, filterGroup.level)}
                                                class:selected={selectedFilters[testId].some(f => f.name === filter && f.level === filterGroup.level)}
                                                style="background-color: {getFilterColor(filterGroup.level)}"
                                        >
                                            {filter}
                                        </button>
                                    {/each}
                                {/each}
                            </div>
                        {/if}
                        <div class="test-methods-container mt-3">
                            {#if testData.notRun}
                                <div class="alert alert-secondary">
                                    <Fa icon={faMinusCircle} class="me-2"/>
                                    This test was not run in this version.
                                </div>
                            {:else}
                                {#each Object.entries(filteredTables[testId]) as [methodName, methodData]}
                                    <div class="test-method-column">
                                        {#each Object.entries(methodData) as [runId, results]}
                                            {#key runId}
                                                <h5 class="mt-3">
                                                    <a href="/tests/scylla-cluster-tests/{runId}" target="_blank"
                                                       class="text-decoration-none">
                                                        {methodName}
                                                    </a>
                                                    {#if currentVersionRuns[testId]?.[methodName]?.status === 'passed'}
                                                        <Fa icon={faCheckCircle} class="text-success ms-2"/>
                                                    {:else if currentVersionRuns[testId]?.[methodName]?.status === 'failed'}
                                                        <Fa icon={faTimesCircle} class="text-danger ms-2"/>
                                                    {:else if currentVersionRuns[testId]?.[methodName]?.status === 'created'}
                                                        <Fa icon={faCircle} class="text-info ms-2"/>
                                                    {:else if currentVersionRuns[testId]?.[methodName]?.status === 'running'}
                                                        <Fa icon={faSpinner} class="text-warning ms-2 fa-spin"/>
                                                    {:else if currentVersionRuns[testId]?.[methodName]?.status === 'aborted'}
                                                        <Fa icon={faBan} class="text-dark ms-2"/>
                                                    {:else if currentVersionRuns[testId]?.[methodName]?.status === 'test_error'}
                                                        <Fa icon={faExclamationCircle} class="text-test-error ms-2"/>
                                                    {:else if currentVersionRuns[testId]?.[methodName]?.status === 'not_run'}
                                                        <Fa icon={faMinusCircle} class="text-secondary ms-2"/>
                                                    {:else if currentVersionRuns[testId]?.[methodName]?.status === 'not_planned'}
                                                        <Fa icon={faMinusCircle} class="text-not-planned ms-2"/>
                                                    {:else if currentVersionRuns[testId]?.[methodName]?.status === 'unknown'}
                                                        <Fa icon={faQuestionCircle} class="text-muted ms-2"/>
                                                    {:else}
                                                        <Fa icon={faExclamationTriangle} class="text-warning ms-2"/>
                                                    {/if}
                                                    (started by {currentVersionRuns[testId]?.[methodName]?.started_by})
                                                    <RunIssues runId={runId} runStatus={currentVersionRuns[testId]?.[methodName]?.status}/>
                                                </h5>
                                                <ul class="result-list list-group">
                                                    {#each results as tableEntry}
                                                        {#each Object.entries(tableEntry) as [table_name, result]}
                                                            <li class="list-group-item">
                                                                <ResultTable
                                                                    {table_name}
                                                                    {result}
                                                                    test_id={testId}
                                                                    bind:selectedScreenshot
                                                                />
                                                            </li>
                                                        {/each}
                                                    {/each}
                                                </ul>
                                            {/key}

                                        {/each}
                                    </div>
                                {/each}
                            {/if}
                        </div>
                    {/if}
                </div>
            {/each}
        </div>
    {/if}
</div>

<style>
    .filters-container {
        display: flex;
        flex-direction: row;
        justify-content: flex-start;
        align-content: flex-start;
        margin-bottom: 20px;
        flex-wrap: wrap;
    }

    .filters-container button {
        margin: 2px;
        padding: 5px 10px;
        cursor: pointer;
        border: 1px solid #6c757d;
        border-radius: 0.25rem;
        background-color: #fff;
        color: #212529;
        font-size: 0.875rem;
    }

    .filters-container button.selected {
        background-color: #0d6efd;
        color: #fff;
        border-color: #0d6efd;
    }

    .filters-container button:hover {
        background-color: #f8f9fa;
    }

    button.colored:not(.selected):not(:hover) {
        background-color: #f0f0f0 !important;
    }

    .test-methods-container {
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
    }

    .test-method-column {
        flex: 1;
        min-width: 300px;
    }

    .result-list {
        padding-left: 0;
    }
</style>
