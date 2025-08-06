<script lang="ts">
    import { createEventDispatcher, onMount } from "svelte";
    import { fade } from "svelte/transition";
    import { sendMessage } from "../Stores/AlertStore";
    import { extractBuildNumber } from "../Common/RunUtils";
    import { InvestigationStatusIcon, StatusBackgroundCSSClassMap } from "../Common/TestStatus";
    import { faChevronCircleDown, faChevronCircleUp } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import TestRuns from "../WorkArea/TestRuns.svelte";

    interface Props {
        jobId?: string;
        jobs?: any;
    }

    let { jobId = "", jobs = [] }: Props = $props();
    const dispatch = createEventDispatcher();
    let testInfo = $state();
    let failedFetch = $state(false);
    let investigating = $state(false);

    const fetchTestInfo = async function () {
        try{
            let res = await fetch(`/api/v1/test-info?testId=${jobId}`);
            if (res.status != 200) throw new Error("HTTP Transport Error");
            let data = await res.json();
            if (data.status != "ok") {
                throw new Error([data.exception, ...data.arguments].join(" "));
            }
            dispatch("testIdResolved", {
                testId: jobId,
                record: data.response,
            });
            return data.response;
        } catch (e) {
            if (e instanceof Error) {
                sendMessage("error", `Error fetching user jobs\n${e.message}`, "ProfileJob::testInfo");
            } else {
                sendMessage("error", "Error fetching user jobs\nUnknown error. Check console for details", "ProfileJobs::testInfo");
            }
            failedFetch = true;
            console.log(e);
        }
    };

    onMount(async () => {
        testInfo = await fetchTestInfo();
    });
</script>

<div class="rounded bg-white p-2 mb-2" transition:fade>
    {#if testInfo}
        <div class="d-flex mb-2">
            <div>
                <h6>{testInfo.test.pretty_name ?? testInfo.test.name}</h6>
                {#if !investigating}
                    <div class="d-flex align-items-center">
                        {#each jobs.slice(0, 5) as job}
                            <div class="{StatusBackgroundCSSClassMap[job.status] ?? StatusBackgroundCSSClassMap.unknown} px-2 py-1 ms-1 rounded-start text-light">
                                #{extractBuildNumber(job)}
                            </div>
                            <div class="bg-dark rounded-end me-1 px-2 py-1 text-light">
                                <Fa icon={InvestigationStatusIcon[job.investigation_status]}/>
                            </div>
                        {/each}
                        {#if jobs.length > 5}
                            <div>...and {Math.max(jobs.length - 5, 0)} more.</div>
                        {/if}
                    </div>
                {/if}
            </div>
            <div class="ms-auto text-end p-2">
                <div>
                    <span class="fw-bold">Release: </span> {testInfo.release.pretty_name ?? testInfo.release.name}
                </div>
                <div>
                    <span class="fw-bold">Group: </span> {testInfo.group.pretty_name ?? testInfo.group.name}
                </div>
            </div>
            <div class="ms-2 text-end align-self-center">
                <button class="btn btn-dark" onclick={() => investigating = !investigating}>
                    {#if investigating}
                        <Fa icon={faChevronCircleUp}/>
                    {:else}
                        <Fa icon={faChevronCircleDown}/>
                    {/if}
                </button>
            </div>
        </div>
        <div class="overflow-hidden rounded border" class:d-none={!investigating}>
            {#if investigating}
            <TestRuns testId={jobId} additionalRuns={jobs.map(v => v.id).slice(0, 5)} on:investigationStatusChange on:batchIgnoreDone/>
            {/if}
        </div>
    {:else}
        {#if failedFetch}
            <div>
                Unable to load test info. The test might have been removed.
                <div>TestId: {jobId}</div>
            </div>
        {:else}
            TestId: {jobId} <div><span class="spinner-grow"></span> Loading...</div>
            <div>
                Total Jobs: {jobs.length}
            </div>
        {/if}
    {/if}
</div>
