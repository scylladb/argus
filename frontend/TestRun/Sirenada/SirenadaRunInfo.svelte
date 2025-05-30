<script>
    import {
        faBusinessTime, faCopy, faPlay,
    } from "@fortawesome/free-solid-svg-icons";
    import humanizeDuration from "humanize-duration";
    import Fa from "svelte-fa";
    import { timestampToISODate } from "../../Common/DateUtils";
    import { extractBuildNumber } from "../../Common/RunUtils";
    import JenkinsBuildModal from "../Jenkins/JenkinsBuildModal.svelte";
    import JenkinsCloneModal from "../Jenkins/JenkinsCloneModal.svelte";
    export let testRun = {};
    export let testInfo;
    export let rebuildRequested = false;
    let cloneRequested = false;

</script>

<div class="container-fluid">
    <div class="row">
        <div class="col-6 p-2">
            <h5>Run Details</h5>
            <ul class="list-unstyled border-start ps-2">
                <li>
                    <span class="fw-bold">Release:</span>
                    {testInfo.release?.name ?? "#NO_RELEASE"}
                </li>
                <li>
                    <span class="fw-bold">Group:</span>
                    {(testInfo.group?.pretty_name || testInfo.group?.name) ?? "#NO_GROUP"}
                </li>
                <li>
                    <span class="fw-bold">Test:</span>
                    {(testInfo.test?.pretty_name || testInfo.test?.name) ?? "#NO_TEST"}
                </li>
                <li>
                    <span class="fw-bold">Id:</span>
                    {testRun.id}
                </li>
                <li>
                    <span class="fw-bold">Start time:</span>
                    {timestampToISODate(testRun.start_time, true)}
                </li>
                {#if new Date(testRun.end_time).getUTCFullYear() != 1970}
                    <li>
                        <span class="fw-bold">End time:</span>
                        {timestampToISODate(testRun.end_time, true)}
                    </li>
                    <li>
                        <span class="fw-bold">Duration:</span>
                        {humanizeDuration(
                            new Date(testRun.end_time) -
                                new Date(testRun.start_time),
                            {
                                round: true,
                                units: ["y", "mo", "w", "d", "h", "m"],
                                largest: 1,
                            }
                        )}
                    </li>
                {/if}
                <li>
                    <span class="fw-bold">Build job:</span>
                    <a href={testRun.build_job_url} target="_blank">
                        {testRun.build_id}
                    </a>
                </li>
            </ul>
        </div>
    </div>
    <div class="row">
        {#if rebuildRequested}
            <JenkinsBuildModal
                buildId={testRun.build_id}
                buildNumber={extractBuildNumber(testRun)}
                pluginName={testInfo.test.plugin_name}
                on:rebuildCancel={() => (rebuildRequested = false)}
                on:rebuildComplete={() => (rebuildRequested = false)}
            />
        {/if}
        {#if cloneRequested}
            <JenkinsCloneModal
                buildId={testRun.build_id}
                buildNumber={extractBuildNumber(testRun)}
                pluginName={testInfo.test.plugin_name}
                testId={testInfo.test.id}
                releaseId={testInfo.release.id}
                groupId={testInfo.group.id}
                oldTestName={testInfo.test.name}
                on:cloneCancel={() => (cloneRequested = false)}
                on:cloneComplete={() => (cloneRequested = false)}
            />
        {/if}
        <div class="col-6 p-2">
            <div class="btn-group">
                <button class="btn btn-sm btn-outline-primary" on:click={() => (rebuildRequested = true)}
                    ><Fa icon={faPlay} /> Rebuild</button
                >
                <button class="btn btn-sm btn-outline-primary" on:click={() => (cloneRequested = true)}
                    ><Fa icon={faCopy} /> Clone</button
                >
                <a
                    href="/dashboard/{testInfo.release.name}"
                    class="btn btn-outline-success"
                    ><Fa icon={faBusinessTime} /> Release Dashboard</a
                >
            </div>
        </div>
    </div>
</div>
