<script>
    import { onDestroy, onMount } from "svelte";
    import { stateEncoder, stateDecoder } from "../Common/StateManagement";
    import { allReleases } from "../Stores/WorkspaceStore";
    import TestRunsPanel from "./TestRunsPanel.svelte";
    import RunRelease from "./RunRelease.svelte";
    let testRuns = {};
    let releases;
    let filterString = "";
    $: releases = $allReleases;

    const isFiltered = function (name = "", filterString = "") {
        if (filterString == "") {
            return false;
        }
        return !RegExp(filterString).test(name);
    };

    const onTestRunRequest = function (event) {
        testRuns[event.detail.uuid] = {
            test: event.detail.test,
            release: event.detail.release,
            group: event.detail.group,
            build_system_id: event.detail.key,
        };
        testRuns = testRuns;
        let state = stateEncoder(testRuns);
        history.pushState({}, "", `?${state}`);
    };

    const onTestRunRemove = function (event) {
        let id = event.detail.runId;
        delete testRuns[id];
        testRuns = testRuns;
        let state = stateEncoder(testRuns);
        history.pushState({}, "", `?${state}`);
    };

    onMount(() => {
        testRuns = stateDecoder();
    });

    onDestroy(() => {
        unsub();
    });
</script>

<svelte:window
    on:popstate={() => {
        testRuns = stateDecoder();
    }}
/>

<div class="container-fluid bg-lighter">
    <div class="row p-4" id="dashboard-main">
        <div
            class="col-3 p-0 py-4 me-3 border rounded shadow-sm bg-white"
            id="run-sidebar"
        >
            {#if releases}
                <div class="p-2">
                    <input
                        class="form-control"
                        type="text"
                        placeholder="Filter releases"
                        bind:value={filterString}
                        on:input={() => {
                            releases = releases;
                        }}
                    />
                </div>
                <div class="accordion accordion-flush" id="releaseAccordion">
                    {#each releases as release (release.id)}
                        <RunRelease
                            {release}
                            on:testRunRequest={onTestRunRequest}
                            filtered={isFiltered(release.name, filterString)}
                            bind:runs={testRuns}
                            on:testRunRemove={onTestRunRemove}
                        />
                    {/each}
                </div>
            {/if}
        </div>
        <div class="col-8 p-2 border rounded shadow-sm bg-main">
            <TestRunsPanel
                bind:test_runs={testRuns}
                on:testRunRemove={onTestRunRemove}
                workAreaAttached={true}
            />
        </div>
    </div>
</div>

<style>
    #run-sidebar {
        height: 960px;
        overflow-y: scroll;
    }
</style>
