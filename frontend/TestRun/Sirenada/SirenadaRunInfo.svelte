<script>
    import {
        faBusinessTime, faPlay,
    } from "@fortawesome/free-solid-svg-icons";
    import humanizeDuration from "humanize-duration";
    import Fa from "svelte-fa";
    import { timestampToISODate } from "../../Common/DateUtils";
    export let testRun = {};
    export let testInfo;

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
        <div class="col-6 p-2">
            <div class="btn-group">
                <a class="btn btn-sm btn-outline-primary" href={`${testRun.build_job_url}rebuild/parameterized`} title="Rebuild"
                    ><Fa icon={faPlay} /> Rebuild</a
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
