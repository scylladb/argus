<script>
    import { onMount } from "svelte";
    import TestRuns from "./TestRuns.svelte";
    import RunRelease from "./RunRelease.svelte";
    import { stats } from "./StatsSubscriber.js";
    let releases = [];
    let test_runs = {};
    let releaseStats = {};
    let filterString = "";
    let filterStringRuns = "";
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

    const fetchNewReleases = function () {
        fetch("/api/v1/releases")
            .then((res) => {
                if (res.status == 200) {
                    return res.json();
                } else {
                    console.log(res);
                }
            })
            .then((res) => {
                console.log(res);
                if (res.status === "ok") {
                    releases = res.response;
                }
            });
    };

    const onTestRunRequest = function (event) {
        console.log(event);
        test_runs[event.detail.uuid] = {
            runs: event.detail.runs,
            test: event.detail.test,
            release: event.detail.release,
        };
    };

    onMount(() => {
        fetchNewReleases();
    });
</script>

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
            {#if Object.keys(test_runs).length > 0}
                <div class="p-2">
                    <input class="form-control" type="text" placeholder="Filter runs" bind:value={filterStringRuns} on:input={() => { test_runs = test_runs }}>
                </div>
                <div class="accordion" id="accordionTestRuns">
                    {#each Object.keys(test_runs) as test_run_id}
                        <TestRuns
                            id={test_run_id}
                            data={test_runs[test_run_id]}
                            parent="#accordionTestRuns"
                            filtered={isFiltered(test_runs[test_run_id].test.name, filterStringRuns)}
                        />
                    {/each}
                </div>
            {:else}
                <div class="row h-100">
                    <div class="col p-4 align-self-center text-center ">
                        <div
                            class="d-inline-block border rounded p-4 text-muted"
                        >
                            Select a test on the left and its runs will appear
                            in this area
                        </div>
                    </div>
                </div>
            {/if}
        </div>
    </div>
</div>

<style>
    .bg-white {
        background-color: #fff;
    }
</style>
