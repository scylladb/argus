<script>
    import Fa from "svelte-fa";
    import { StatusBackgroundCSSClassMap } from "./TestStatus";
    import { faExternalLinkSquareAlt } from "@fortawesome/free-solid-svg-icons";
    import TestRun from "./TestRun.svelte";
    export let runs = [];
    const getBuildNumber = function (url) {
        return url
            .trim()
            .slice(0, url.length - 1)
            .split("/")
            .at(-1);
    };
    let clickedRuns = {};
</script>

<div class="container bg-white border rounded my-4 shadow-sm min-vh-100">
    {#each runs as run}
        <div class="row mb-3 p-4">
            <div class="col border rounded">
                <div class="d-flex p-2 align-items-center">
                    <div
                        class="me-2 p-2 border rounded {StatusBackgroundCSSClassMap[
                            run.status
                        ]} text-light"
                    >
                        {run.status.toUpperCase()}
                    </div>
                    <h3 class="me-4 p-2">
                        <span class="text-muted">{run.build_job_name}#</span>{getBuildNumber(run.build_job_url)}
                    </h3>
                    <div class="me-4">
                        <h6 class="text-muted">Started at</h6>
                        <div>
                            {new Date(run.start_time * 1000).toLocaleString(
                                "en-CA"
                            )}
                        </div>
                    </div>
                    <div class="ms-auto">
                        <div class="btn-group">
                            <button
                                class="btn btn-sm btn-secondary"
                                data-bs-toggle="collapse"
                                data-bs-target="#testRun_{run.id}"
                                on:click={() => clickedRuns[run.id] = true}
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
                        <TestRun id={run.id} build_number={getBuildNumber(run.build_job_url)} />
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
</div>
