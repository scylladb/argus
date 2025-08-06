<script lang="ts">
    import {
        faBusinessTime,
    } from "@fortawesome/free-solid-svg-icons";
    import humanizeDuration from "humanize-duration";
    import Fa from "svelte-fa";
    import { timestampToISODate } from "../../Common/DateUtils";
    let {
        test_run = {},
        release,
        group,
        test
    } = $props();
</script>

<div class="container-fluid">
    <div class="row">
        <div class="col-6 p-2">
            <h5>Run Details</h5>
            <ul class="list-unstyled border-start ps-2">
                <li>
                    <span class="fw-bold">Release:</span>
                    {release?.name ?? "#NO_RELEASE"}
                </li>
                <li>
                    <span class="fw-bold">Group:</span>
                    {(group?.pretty_name || group?.name) ?? "#NO_GROUP"}
                </li>
                <li>
                    <span class="fw-bold">Test:</span>
                    {(test?.pretty_name || test?.name) ?? "#NO_TEST"}
                </li>
                <li>
                    <span class="fw-bold">Id:</span>
                    {test_run.id}
                </li>
                <li>
                    <span class="fw-bold">Start time:</span>
                    {timestampToISODate(test_run.start_time, true)}
                </li>
                {#if new Date(test_run.end_time).getUTCFullYear() != 1970}
                    <li>
                        <span class="fw-bold">End time:</span>
                        {timestampToISODate(test_run.end_time, true)}
                    </li>
                    <li>
                        <span class="fw-bold">Duration:</span>
                        {humanizeDuration(
                            new Date(test_run.end_time) -
                                new Date(test_run.start_time),
                            {
                                round: true,
                                units: ["y", "mo", "w", "d", "h", "m"],
                                largest: 1,
                            }
                        )}
                    </li>
                {/if}
                <li>
                    <span class="fw-bold">Started by:</span>
                    {test_run.started_by ?? "Unknown, probably jenkins"}
                </li>
                <li>
                    <span class="fw-bold">Build job:</span>
                    <a href={test_run.build_job_url} target="_blank">
                        {test_run.build_id}
                    </a>
                </li>
            </ul>
        </div>
        <div class="col-6 p-2">
            <h5>Build Info</h5>
            <ul class="list-unstyled border-start ps-2">
                <li>
                    <span class="fw-bold">Scylla Version:</span>
                    {test_run.scylla_version}
                </li>
            </ul>
        </div>
    </div>
    <div class="row">
        <div class="col-6 p-2">
            <div class="btn-group">
                <a
                    href="/dashboard/{release.name}"
                    class="btn btn-outline-success"
                    ><Fa icon={faBusinessTime} /> Release Dashboard</a
                >
            </div>
        </div>
    </div>
</div>
