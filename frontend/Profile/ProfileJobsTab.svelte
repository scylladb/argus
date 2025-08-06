<script lang="ts">
    import { run } from 'svelte/legacy';

    import { faCircle, faInfoCircle} from "@fortawesome/free-solid-svg-icons";
    import ProfileJob from "./ProfileJob.svelte";
    import Fa from "svelte-fa";
    import { InvestigationStatusIcon, StatusCSSClassMap, TestInvestigationStatus, TestStatus } from "../Common/TestStatus";
    import { titleCase } from "../Common/TextUtils";
    import { createEventDispatcher } from "svelte";

    let { jobs = $bindable([]), filterExpr = () => true } = $props();
    const dispatch = createEventDispatcher();
    let currentPage = $state(0);
    let pagedData = $state([]);
    let filterString = $state("");
    let testIdMap = {};
    let releaseIdMap = $state({});
    let allVersions = $state({});

    let enabledReleases = $state({});
    let enabledVersions = $state({});
    let stats = $state({});

    const testIdResolved = function(e) {
        let testInfo = e.detail.record;
        let testId = e.detail.testId;
        if (!testIdMap[testId]) {
            testIdMap[testId] = testInfo.test.name;
        }

        if (!releaseIdMap[testInfo.release.id]) {
            releaseIdMap[testInfo.release.id] = testInfo.release.name;
        }
    };

    /**
     *
     * @param {string} filterString
     * @param {string} testName
     */
    const shouldFilter = function (filterString, testName) {
        if (!filterString) return false;
        if (!testName) return false;
        return testName.toLowerCase().search(filterString) == -1;
    };

    /**
     * Filters by expr and aggregates jobs by job id
     * @param {Object[]} jobs
     * @param expr
     */
    const filterAndAggregateJobs = function (jobs, expr, filterString) {
        const filteredJobs = jobs.filter(expr);
        return filteredJobs.reduce((acc, job) => {
            const resolvedName = testIdMap[job.test_id];
            if (shouldFilter(filterString, resolvedName)) return acc;
            if (!acc[job.test_id]) {
                acc[job.test_id] = [];
            }
            acc[job.test_id].push(job);
            return acc;
        }, {});
    };

    /**
     * Split an array into 2D array of "pages"
     * @param {{ string: Object }} jobs
     */
    const paginateData = function (jobs) {
        let allJobs = Object.entries(jobs).sort((a, b) => b[1].length - a[1].length);
        const PAGE_SIZE = 10;
        const steps = Math.max(parseInt(allJobs.length / PAGE_SIZE) + 1, 1);
        const pages = Array
            .from({length: steps}, () => [])
            .map((_, pageIdx) => {
                const sliceIdx = pageIdx * PAGE_SIZE;
                const slice = allJobs.slice(sliceIdx, PAGE_SIZE + sliceIdx);
                return [...slice];
            });
        return pages;
    };

    const selectPage = function(pagedData, page) {
        let selectedPage = pagedData[page] ?? [];
        return selectedPage;
    };

    const collectVersions = function (jobs) {
        return jobs
            .map(v => [v.release_id, v.scylla_version])
            .reduce((acc, [releaseId, productVersion]) => {
                let store = acc[releaseId] ?? [];
                if (!store.includes(productVersion)) {
                    store.push(productVersion);
                    enabledVersions[productVersion] = enabledVersions[productVersion] ?? true;
                }
                acc[releaseId] = store;
                return acc;
            }, {});
    };

    const prepareFilters = function(jobs) {
        allVersions = collectVersions(jobs);
        enabledReleases = Object.fromEntries(jobs.map(v => [v.release_id, enabledReleases[v.release_id] ?? true]));
    };

    const filterJobsByBranchOrVersion = function(jobs) {
        return jobs.filter(v => enabledReleases[v.release_id] && enabledVersions[v.scylla_version]);
    };

    const flattenVersions = function(versions, enabledReleases) {
        let flattenedVersions = [];
        Object.entries(versions).forEach(([releaseId, versions]) => {
            if (enabledReleases[releaseId]) {
                versions.forEach(v => {
                    if (!flattenedVersions.includes(v)) {
                        flattenedVersions.push(v);
                    }
                });
            }
        });

        return flattenedVersions.sort((a, b) => a?.localeCompare(b) ?? 0);
    };

    const prepareStats = function(jobs, enabledReleases, enabledVersions) {
        let stats = jobs.reduce((acc, v) => {
            if (enabledReleases[v.release_id] && enabledVersions[v.scylla_version]) {
                acc[v.status] = (acc[v.status] ?? 0) + 1;
                acc[v.investigation_status] = (acc[v.investigation_status] ?? 0) + 1;
            }
            return acc;
        }, {});
        return stats;
    };

    const selectOneVersion = function(version) {
        for (const key in enabledVersions) {
            if (key != version) {
                enabledVersions[key] = false;
            }
        }
        enabledVersions[version] = true;
    };

    const selectOneRelease = function(releaseId) {
        for (const key in enabledReleases) {
            if (key != releaseId) {
                enabledReleases[key] = false;
            }
        }
        enabledReleases[releaseId] = true;
    };

    const onInvestigationStatusChange = function(e) {
        let jobId = e.detail.runId;
        let newStatus = e.detail.status;
        let jobIdx = jobs.findIndex(v => v.id == jobId);
        if (jobIdx >= 0) {
            jobs[jobIdx].investigation_status = newStatus;
            jobs = jobs;
        }
        stats = prepareStats(jobs, enabledReleases, enabledVersions);
        dispatch("investigationStatusChange", e.detail);
    };


    run(() => {
        prepareFilters(jobs);
    });
    run(() => {
        pagedData = paginateData(filterAndAggregateJobs(filterJobsByBranchOrVersion(jobs, enabledReleases, enabledVersions), filterExpr, filterString));
    });
    run(() => {
        stats = prepareStats(jobs, enabledReleases, enabledVersions);
    });
</script>

<div class="mb-2 p-2">
    <input type="text" bind:value={filterString} placeholder="Filter tests by name" class="form-control">
</div>
<div class="mb-2">
    <div class="text-end">
        <div class="d-inline-flex mb-2 align-items-center justify-content-end bg-white border rounded overflow-hidden p-2">
            {#each Object.values(TestStatus) as status}
                {#if stats[status]}
                    <div title={titleCase(status)} class="d-flex align-items-center ms-1">
                        <Fa icon={faCircle} class="{StatusCSSClassMap[status]} ms-1"/>
                        <div class="ms-1">{stats[status] ?? 0}</div>
                    </div>
                {/if}
            {/each}
            {#each Object.values(TestInvestigationStatus) as status}
                {#if stats[status]}
                    <div title={titleCase(status)} class="d-flex align-items-center ms-1">
                        <Fa icon={InvestigationStatusIcon[status]} class="{StatusCSSClassMap[status]} ms-1"/>
                        <div class="ms-1">{stats[status] ?? 0}</div>
                    </div>
                {/if}
            {/each}
        </div>
    </div>
    <div title="Double click a release to select only that release">
        <Fa icon={faInfoCircle}/>
    </div>
    <div class="d-flex flex-wrap mb-2">
        {#each Object.keys(enabledReleases) as releaseId}
            {@const releaseName = releaseIdMap[releaseId] ?? releaseId}
            <button
                class="btn btn-{enabledReleases[releaseId] ? "success" : "light"} ms-2 mb-2 text-truncate"
                title="Branch {releaseName}"
                style="flex: 0 0 15%"
                onclick={() => (enabledReleases[releaseId] = !enabledReleases[releaseId])}
                ondblclick={() => (selectOneRelease(releaseId))}
            >
                {releaseName}
            </button>
        {/each}
    </div>
    <div title="Double click a version to select only that version">
        <Fa icon={faInfoCircle}/>
    </div>
    <div class="d-flex flex-wrap">
        {#each flattenVersions(allVersions, enabledReleases) as version}
            <button
                class="btn btn-{enabledVersions[version] ? "primary" : "light"} ms-2 mb-2"
                style="flex: 0 0 10%"
                title="Product Version"
                onclick={() => (enabledVersions[version] = !enabledVersions[version])}
                ondblclick={() => (selectOneVersion(version))}
            >
                {version ? version : "No version"}
            </button>
        {:else}
            <div class="p-4 text-muted text-center">
                No versions to display
            </div>
        {/each}
    </div>
</div>
{#each selectPage(pagedData, currentPage) as [jobId, jobs] (jobId) }
    <ProfileJob {jobId} {jobs} on:testIdResolved={testIdResolved} on:investigationStatusChange={onInvestigationStatusChange} on:batchIgnoreDone/>
{:else}
    <div class="text-muted text-center p-4">
        Nothing to investigate.
    </div>
{/each}
{#if pagedData.length > 1}
    <div class="d-flex flex-wrap">
        {#each pagedData as _, idx}
            <button
                class="me-2 btn btn-sm btn-primary p-1 mb-1"
                style="flex: 0 0 2.5%;"
                onclick={() => (currentPage = idx)}
            >
                {idx + 1}
            </button>
        {/each}
    </div>
{/if}
