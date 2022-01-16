<script>
    import { onMount } from "svelte";
    import { Base64 } from "js-base64";
    import { stats } from "../Stores/StatsSubscriber";
    import { sendMessage } from "../Stores/AlertStore";
    import TestRunsPanel from "./TestRunsPanel.svelte";
    import RunRelease from "./RunRelease.svelte";
    let releases = [];
    let test_runs = {};
    let releaseStats = {};
    let filterString = "";

    const stateUpdater = function() {
        let state = JSON.stringify(test_runs);
        let encodedState = Base64.encode(state, true);
        console.log("Encoded state length: %d", encodedState.length);
        history.pushState({}, "", `?state=${encodedState}`);
    };

    const stateDecoder = function () {
        let params = new URLSearchParams(document.location.search);
        let state = params.get("state");
        if (state) {
            let decodedState = JSON.parse(Base64.decode(state));
            console.log(decodedState);
            test_runs = decodedState;
            return;
        }

        test_runs = {};
    }

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
            console.log(apiJson);
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
        console.log(event);
        test_runs[event.detail.uuid] = {
            runs: event.detail.runs,
            test: event.detail.test,
            release: event.detail.release,
        };
        test_runs = test_runs;
        stateUpdater();

    };

    onMount(() => {
        fetchNewReleases();
        stateDecoder();
        window.onpopstate = stateDecoder();
    });



</script>
<svelte:window on:popstate={stateDecoder}/>

<div class="container-fluid bg-light">
    <div class="row p-4" id="dashboard-main">
        <div
            class="col-3 p-0 py-4 min-vh-100 me-3 border rounded shadow-sm bg-white"
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
                    />
                {/each}
            </div>
        </div>
        <div class="col-8 p-2 border rounded shadow-sm bg-white">
            <TestRunsPanel bind:test_runs={test_runs}/>
        </div>
    </div>
</div>

<style>
    .bg-white {
        background-color: #fff;
    }
</style>
