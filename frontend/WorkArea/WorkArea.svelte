<script>
    import { onMount } from "svelte";
    import queryString from "query-string";
    import { stateEncoder, stateDecoder } from "../Common/StateManagement";
    import TestRunsPanel from "./TestRunsPanel.svelte";
    import RunRelease from "./RunRelease.svelte";
    let testRuns = $state([]);
    let releases = $state();
    let filterString = $state("");

    const fetchReleases = async function() {
        let res = await fetch("/api/v1/releases");
        if (res.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await res.json();
        if (json.status != "ok") {
            return Promise.reject(json.exception);
        }
        releases = json.response;

    };

    const isFiltered = function (name = "", filterString = "") {
        if (filterString == "") {
            return false;
        }
        return !RegExp(filterString).test(name);
    };

    const onTestRunRequest = function (event) {
        if (testRuns.find(v => v == event.detail.testId)) return;
        testRuns.push(event.detail.testId);
        testRuns = testRuns;
        let state = stateEncoder(testRuns);
        let params = queryString.parse(document.location.search, {arrayFormat: "bracket"});
        params.state = state;
        history.pushState({}, "", `?${queryString.stringify(params, {arrayFormat: "bracket"})}`);
    };

    const onTestRunRemove = function (event) {
        let id = event.detail.testId;
        testRuns = testRuns.filter(v => v != id);
        let state = stateEncoder(testRuns);
        let params = queryString.parse(document.location.search, {arrayFormat: "bracket"});
        params.state = state;
        history.pushState({}, "", `?${queryString.stringify(params, {arrayFormat: "bracket"})}`);
    };

    onMount(() => {
        testRuns = stateDecoder();
    });

</script>

<svelte:window
    onpopstate={() => {
        testRuns = stateDecoder();
    }}
/>

<div class="container-fluid bg-lighter">
    <div class="row p-4" id="dashboard-main">
        <div
            class="col-md-3 p-0 py-4 me-3 border rounded shadow-sm bg-white"
            id="run-sidebar"
        >
            {#await fetchReleases()}
                <div class="d-flex align-items-center justify-content-center">
                    <div class="spinner-border"></div>
                    <div class="ms-2">Fetching releases...</div>
                </div>
            {:then}
                <div class="p-2">
                    <input
                        class="form-control"
                        type="text"
                        placeholder="Filter releases"
                        bind:value={filterString}
                        oninput={() => {
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
            {/await}
        </div>
        <div class="col-md-8 col-sm-12 p-2 border rounded shadow-sm bg-main">
            <TestRunsPanel
                bind:testRuns={testRuns}
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

    @media screen and (max-width: 768px) {
        #run-sidebar {
            display: none
        }
    }
</style>
