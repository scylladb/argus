<script>
    export let runs = [];
    import Fa from "svelte-fa";
    import { StatusCSSClassMap } from "../Common/TestStatus";
    import { faCircle, faExternalLinkSquareAlt } from "@fortawesome/free-solid-svg-icons";
    import TestRuns from "../WorkArea/TestRuns.svelte";
    import { timestampToISODate } from "../Common/DateUtils";
    let filterString = "";

    const filterJob = function (job) {
        let jobName = `${job.build_id}#${getBuildNumber(
            job.build_job_url
        )}`;
        if (filterString == "") {
            return false;
        }
        try {
            return !RegExp(filterString.toLowerCase()).test(
                jobName.toLowerCase()
            );
        } catch (e) {
            return true;
        }
    };

    const getBuildNumber = function (url) {
        return url
            .trim()
            .slice(0, url.length - 1)
            .split("/")
            .at(-1);
    };

    const fetchReleaseDetails = async function(releaseId) {
        let res = await fetch(`/api/v1/release/${releaseId}/details`);
        if (res.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await res.json();
        if (json.status != "ok") {
            return Promise.reject(json.exception);
        }

        return json.response;
    };

    const fetchTestDetails = async function(testId) {
        let res = await fetch(`/api/v1/test/${testId}/details`);
        if (res.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await res.json();
        if (json.status != "ok") {
            return Promise.reject(json.exception);
        }

        return json.response;
    };

    let clickedRuns = {};
</script>

{#if runs.length > 1}
    <div class="row mb-2">
        <input
            class="form-control"
            type="text"
            placeholder="Filter by name"
            on:keyup={(e) => {
                filterString = e.target.value;
                runs = runs;
            }}
        />
    </div>
{/if}

{#each runs as run}
    <div class="row" class:d-none={filterJob(run)}>
        <div class="col shadow rounded bg-white mb-2">
            <div class="row p-2">
                <h3 class="col-9 d-flex align-items-center">
                    <div title={run.status}>
                        <Fa icon={faCircle} class={StatusCSSClassMap[run.status]} />
                    </div>
                    <div class="ms-3">
                        {#await Promise.all([fetchTestDetails(run.test_id), fetchReleaseDetails(run.release_id)])}
                            <span class="spinner-border spinner-border-sm"></span> Getting name...
                        {:then [test, release]}
                            <div>
                                {test.name}<span class="text-muted">#{getBuildNumber(run.build_job_url)}</span>
                            </div>
                            <div class="text-muted" style="font-size: 0.75em;">
                                {release.name}
                            </div>
                        {/await}
                    </div>
                </h3>
                <div class="col-2">
                    <h6 class="text-muted">Started at</h6>
                    <div>
                        {timestampToISODate(run.start_time , true)}
                    </div>
                </div>
                <div class="col-1">
                    <div class="btn-group d-flex align-items-center h-100">
                        <button
                            class="btn btn-sm btn-outline-secondary"
                            data-bs-toggle="collapse"
                            data-bs-target="#testRun_{run.id}"
                            on:click={() => (clickedRuns[run.id] = !clickedRuns[run.id])}
                        >
                            {clickedRuns[run.id] ? "Close" : "Open"}
                        </button>
                        <a
                            href="/test/{run.test_id}/runs?additionalRuns[]={run.id}"
                            class="btn btn-sm btn-outline-secondary"
                            ><Fa icon={faExternalLinkSquareAlt} /></a
                        >
                    </div>
                </div>
            </div>
            <div class="collapse" id="testRun_{run.id}">
                {#if clickedRuns[run.id]}
                    <TestRuns
                        testId={run.test_id}
                        additionalRuns={[run.id]}
                    />
                {/if}
            </div>
        </div>
    </div>
{:else}
    <div class="row">
        <div class="col my-5">
            <h1 class="text-muted text-center">Nothing to do!</h1>
        </div>
    </div>
{/each}
