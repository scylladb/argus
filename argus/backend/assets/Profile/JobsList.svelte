<script>
    export let runs = [];
    import Fa from "svelte-fa";
    import { StatusBackgroundCSSClassMap } from "../Common/TestStatus";
    import { faExternalLinkSquareAlt } from "@fortawesome/free-solid-svg-icons";
    import TestRun from "../TestRun/TestRun.svelte";
    import { timestampToISODate } from "../Common/DateUtils";
    let filterString = "";

    const filterJob = function (job) {
        let jobName = `${job.build_job_name}#${getBuildNumber(
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
        <div class="col border rounded mb-2">
            <div class="d-flex align-items-center">
                <div
                    class="p-2 border rounded {StatusBackgroundCSSClassMap[
                        run.status
                    ]} text-light text-center"
                    style="width: 156px"
                >
                    {run.status.toUpperCase()}
                </div>
                <h3 class="ms-2 p-2">
                    <span class="text-muted">{run.build_job_name}#</span
                    >{getBuildNumber(run.build_job_url)}
                </h3>
                <div class="ms-auto">
                    <h6 class="text-muted">Started at</h6>
                    <div>
                        {timestampToISODate(run.start_time * 1000, true)}
                    </div>
                </div>
                <div class="ms-2">
                    <div class="btn-group">
                        <button
                            class="btn btn-sm btn-secondary"
                            data-bs-toggle="collapse"
                            data-bs-target="#testRun_{run.id}"
                            on:click={() => (clickedRuns[run.id] = true)}
                            >Open</button
                        >
                        <a
                            href="/test_run/{run.id}"
                            class="btn btn-sm btn-secondary"
                            ><Fa icon={faExternalLinkSquareAlt} /></a
                        >
                    </div>
                </div>
            </div>
            <div class="collapse" id="testRun_{run.id}">
                {#if clickedRuns[run.id]}
                    <TestRun
                        id={run.id}
                        build_number={getBuildNumber(run.build_job_url)}
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
