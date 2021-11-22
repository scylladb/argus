<script>
    import { onMount } from "svelte";
    import TestRuns from "./TestRuns.svelte";
    import RunRelease from "./RunRelease.svelte";
    import { stats } from "./StatsSubscriber.js";
    let releases = [];
    let test_runs = {};
    let releaseStats = {};
    stats.subscribe(value => {
        releaseStats = value.releases;
        releases = releases.sort((a, b) => {
            let leftOrder = releaseStats[a.name]?.total ?? 0;
            let rightOrder = releaseStats[b.name]?.total ?? 0;
            if (leftOrder > rightOrder) {
                return -1;
            } else if (rightOrder > leftOrder) {
                return 1;
            } else {
                return 0;
            }
        })
    });

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
            release: event.detail.release
        };
    };

    onMount(() => {
        fetchNewReleases();
    });
</script>

<div class="container-fluid p-0">
    <div class="row" id="dashboard-main">
        <div class="col-3 p-0 min-vh-100" id="run-sidebar">
            <div class="accordion accordion-flush border" id="releaseAccordion">
                {#each releases as release (release.id)}
                    <RunRelease {release} on:testRunRequest={onTestRunRequest}/>
                {/each}
            </div>
        </div>
        <div class="col-9 p-0">
            {#if Object.keys(test_runs).length > 0}
                <div class="accordion accordion-flush" id="accordionTestRuns">
                    {#each Object.keys(test_runs) as test_run_id}
                        <TestRuns
                            id={test_run_id}
                            data={test_runs[test_run_id]}
                            parent="#accordionTestRuns"
                        />
                    {/each}
                </div>
            {:else}
                <div class="row h-100">
                    <div class="col p-4 align-self-center text-center ">
                        <div
                            class="d-inline-block border rounded p-4 text-muted"
                        >
                            Select a run on the left and it will appear in this
                            area
                        </div>
                    </div>
                </div>
            {/if}
        </div>
    </div>
</div>

<style>
    #dashboard-main {
    }
    #run-sidebar {
        border-right: 1px solid gray;
    }

</style>
