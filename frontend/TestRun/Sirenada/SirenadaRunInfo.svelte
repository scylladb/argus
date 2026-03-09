<script lang="ts">
    import {
        faBusinessTime, faCopy, faPlay,
    } from "@fortawesome/free-solid-svg-icons";
    import humanizeDuration from "humanize-duration";
    import Fa from "svelte-fa";
    import { timestampToISODate } from "../../Common/DateUtils";
    import JenkinsBuildModal from "../Jenkins/JenkinsBuildModal.svelte";
    import JenkinsCloneModal from "../Jenkins/JenkinsCloneModal.svelte";
    interface Props {
        testRun?: any;
        testInfo: any;
        rebuildRequested?: boolean;
    }

    let { testRun = {}, testInfo, rebuildRequested = $bindable(false) }: Props = $props();
    let innerWidth = $state(0);
    let mobile = $derived(innerWidth < 768);
    let cloneRequested = $state(false);

</script>

<svelte:window bind:innerWidth={innerWidth} />

<div class="container-fluid">
    <div class="row">
        <div class="col-12 col-md-6 p-2">
            <h5>Run Details</h5>
            <ul class="list-unstyled border-start ps-2 text-break">
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
                buildNumber={testRun.build_number}
                pluginName={testInfo.test.plugin_name}
                on:rebuildCancel={() => (rebuildRequested = false)}
                on:rebuildComplete={() => (rebuildRequested = false)}
            />
        {/if}
        {#if cloneRequested}
            <JenkinsCloneModal
                buildId={testRun.build_id}
                buildNumber={testRun.build_number}
                pluginName={testInfo.test.plugin_name}
                testId={testInfo.test.id}
                releaseId={testInfo.release.id}
                groupId={testInfo.group.id}
                oldTestName={testInfo.test.name}
                on:cloneCancel={() => (cloneRequested = false)}
                on:cloneComplete={() => (cloneRequested = false)}
            />
        {/if}
        <div class="col-12 col-md-6 p-2">
            {#if mobile}
                <div class="dropdown">
                    <button class="btn btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                        Actions
                    </button>
                    <ul class="dropdown-menu">
                        <li>
                            <button class="dropdown-item" onclick={() => (rebuildRequested = true)}
                                ><Fa icon={faPlay} /> Rebuild</button>
                        </li>
                        <li>
                            <button class="dropdown-item" onclick={() => (cloneRequested = true)}
                                ><Fa icon={faCopy} /> Clone</button>
                        </li>
                        <li>
                            <a
                                class="dropdown-item"
                                href="/dashboard/{testInfo.release.name}"
                            ><Fa icon={faBusinessTime} /> Release Dashboard</a>
                        </li>
                    </ul>
                </div>
            {:else}
                <div class="btn-group">
                    <button class="btn btn-sm btn-outline-primary" onclick={() => (rebuildRequested = true)}
                        ><Fa icon={faPlay} /> Rebuild</button
                    >
                    <button class="btn btn-sm btn-outline-primary" onclick={() => (cloneRequested = true)}
                        ><Fa icon={faCopy} /> Clone</button
                    >
                    <a
                        href="/dashboard/{testInfo.release.name}"
                        class="btn btn-outline-success"
                        ><Fa icon={faBusinessTime} /> Release Dashboard</a
                    >
                </div>
            {/if}
        </div>
    </div>
</div>
