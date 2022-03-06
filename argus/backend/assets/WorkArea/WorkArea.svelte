<script>
    import { onMount } from "svelte";
    import { stateEncoder, stateDecoder} from "../Common/StateManagement";
    import { stats } from "../Stores/StatsSubscriber";
    import { sendMessage } from "../Stores/AlertStore";
    import TestRunsPanel from "./TestRunsPanel.svelte";
    import RunRelease from "./RunRelease.svelte";
    let releases = [];
    let test_runs = {};
    let releaseStats = {};
    let filterString = "";

    stats.subscribe((value) => {
        releaseStats = value.releases;
        releases = releases.sort((a, b) => {
            let leftOrder =
                releaseStats[a.name]?.total - releaseStats[a.name]?.not_run ??
                0;
            let rightOrder =
                releaseStats[b.name]?.total - releaseStats[b.name]?.not_run ??
                0;
            if (leftOrder > rightOrder) {
                return -1;
            } else if (rightOrder > leftOrder) {
                return 1;
            } else {
                return 0;
            }
        });
    });

    const isFiltered = function(name = "", filterString = "") {
        if (filterString == "") {
            return false;
        }
        return !RegExp(filterString).test(name);
    };

    const fetchNewReleases = async function () {
        try {
            let apiResponse = await fetch("/api/v1/releases");
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                releases = apiJson.response;
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage("error", `API Error when fetching releases.\nMessage: ${error.response.arguments[0]}`);
            } else {
                sendMessage("error", "A backend error occurred during release fetch");
            }
        }
    };

    const onTestRunRequest = function (event) {
        test_runs[event.detail.uuid] = {
            test: event.detail.test,
            release: event.detail.release,
            group: event.detail.group,
        };
        test_runs = test_runs;
        let state = stateEncoder(test_runs);
        history.pushState({}, "", `?${state}`);

    };

    const onTestRunRemove = function(event) {
        let id = event.detail.runId;
        delete test_runs[id];
        test_runs = test_runs;
        let state = stateEncoder(test_runs);
        history.pushState({}, "", `?${state}`);
    };

    onMount(() => {
        fetchNewReleases();
        test_runs = stateDecoder();
    });
</script>
<svelte:window on:popstate={() => { test_runs = stateDecoder() }}/>

<div class="container-fluid bg-light">
    <div class="row p-4" id="dashboard-main">
        <div
            class="col-3 p-0 py-4 me-3 border rounded shadow-sm bg-white"
            id="run-sidebar"
        >
            <div class="p-2">
                <input class="form-control" type="text" placeholder="Filter releases" bind:value={filterString} on:input={() => { releases = releases }}>
            </div>
            <div class="accordion accordion-flush" id="releaseAccordion">
                {#each releases as release (release.id)}
                    <RunRelease
                        {release}
                        on:testRunRequest={onTestRunRequest}
                        filtered={isFiltered(release.name, filterString)}
                        bind:runs={test_runs}
                        on:testRunRemove={onTestRunRemove}
                    />
                {/each}
            </div>
        </div>
        <div class="col-8 p-2 border rounded shadow-sm bg-white">
            <TestRunsPanel bind:test_runs={test_runs} on:testRunRemove={onTestRunRemove} workAreaAttached={true}/>
        </div>
    </div>
</div>

<style>
    .bg-white {
        background-color: #fff;
    }

    #run-sidebar {
        height: 960px;
        overflow-y: scroll;
    }
</style>
