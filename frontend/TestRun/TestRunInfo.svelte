<script lang="ts">
    import { run } from 'svelte/legacy';

    import {
        faBusinessTime,
        faSearch,
        faCopy,
        faPlay,
    } from "@fortawesome/free-solid-svg-icons";
    import humanizeDuration from "humanize-duration";
    import Fa from "svelte-fa";
    import { InProgressStatuses } from "../Common/TestStatus";
    import { timestampToISODate } from "../Common/DateUtils";
    import { getScyllaPackage, getKernelPackage, getUpgradedScyllaPackage,
        getOperatorPackage, getOperatorHelmPackage, getOperatorHelmRepoPackage, extractBuildNumber,
    } from "../Common/RunUtils";
    import JenkinsBuildModal from "./Jenkins/JenkinsBuildModal.svelte";
    import JenkinsCloneModal from "./Jenkins/JenkinsCloneModal.svelte";
    import { createEventDispatcher } from "svelte";
    import { sendMessage } from "../Stores/AlertStore";
    let {
        test_run = {},
        release,
        group,
        test
    } = $props();
    let rebuildRequested = $state(false);
    let cloneRequested = $state(false);
    const dispatch = createEventDispatcher();

    let cmd_hydraInvestigateShowMonitor = `hydra investigate show-monitor ${test_run.id}`;
    let cmd_hydraInvestigateShowLogs = `hydra investigate show-logs ${test_run.id}`;

    const locateGrafanaNode = function () {
        return test_run.allocated_resources.find((node) => {
            return new RegExp(/-monitor-node-/).test(node.name) && node.state === "running";
        });
    };

    let scyllaPackage = $state(getScyllaPackage(test_run.packages));
    run(() => {
        scyllaPackage = getScyllaPackage(test_run.packages);
    });

    let operatorPackage = $state(getOperatorPackage(test_run.packages));
    run(() => {
        operatorPackage = getOperatorPackage(test_run.packages);
    });
    let operatorHelmPackage = $state(getOperatorHelmPackage(test_run.packages));
    run(() => {
        operatorHelmPackage = getOperatorHelmPackage(test_run.packages);
    });
    let operatorHelmRepoPackage = $state(getOperatorHelmRepoPackage(test_run.packages));
    run(() => {
        operatorHelmRepoPackage = getOperatorHelmRepoPackage(test_run.packages);
    });

    let kernelPackage = $state(getKernelPackage(test_run.packages));
    run(() => {
        kernelPackage = getKernelPackage(test_run.packages);
    });
    let upgradedPackage = $state(getUpgradedScyllaPackage(test_run.packages));
    run(() => {
        upgradedPackage = getUpgradedScyllaPackage(test_run.packages);
    });
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
                {#if test_run.test_method}
                    <li class="text-break">
                        <span class="fw-bold">Test Method:</span>
                        {test_run.test_method}
                    </li>
                {/if}
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
                {#if test_run.stress_duration}
                    <li>
                        <span class="fw-bold">Custom Stress Duration:</span>
                        {test_run.stress_duration}
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
            <h5>System Information</h5>
            <ul class="list-unstyled border-start ps-2">
                <li>
                    <span class="fw-bold">Backend:</span>
                    {test_run.cloud_setup?.backend ?? "Unknown"}
                </li>
                <li>
                    <span class="fw-bold">Region:</span>
                    {test_run.region_name.join(", ") || "Unknown region"}
                </li>
                <li>
                    <span class="fw-bold">Image id:</span>
                    {test_run.cloud_setup?.db_node.image_id ?? "Unknown"}
                </li>
                <li>
                    <span class="fw-bold">SCT commit sha:</span>
                    {test_run.scm_revision_id ?? "Unknown"}
                </li>
                <li>
                    <span class="fw-bold">SCT repository:</span>
                    {test_run.origin_url ?? "Unset"}
                </li>
                <li>
                    <span class="fw-bold">SCT branch name:</span>
                    {test_run.branch_name ?? "Unset"}
                </li>
                <!-- Scylla v4.5.3-0.20211223.c8f14886d (ami-0df0fbe3daf5ad63d) -->
                {#if test_run.packages}
                    {#if kernelPackage}
                        <li>
                            <span class="fw-bold">Kernel version:</span>
                            {kernelPackage.version}
                        </li>
                    {/if}
                    {#if scyllaPackage}
                        <li>
                            <span class="fw-bold">{ upgradedPackage ? "Base scylla" : "Scylla"} version:</span>
                            {scyllaPackage?.version}-{scyllaPackage?.date}.{scyllaPackage?.revision_id}
                        </li>
                        {#if scyllaPackage?.build_id}
                            <li>
                                <span class="fw-bold">Build id:</span>
                                {scyllaPackage?.build_id}
                            </li>
                        {/if}
                    {/if}
                    {#if operatorPackage}
                        <li>
                            <span class="fw-bold">Operator Image:</span>
                            {operatorPackage.version}
                        </li>
                    {/if}
                    {#if operatorHelmPackage}
                        <li>
                            <span class="fw-bold">Operator Helm Version:</span>
                            {operatorHelmPackage.version}
                        </li>
                    {/if}
                    {#if operatorHelmRepoPackage}
                        <li>
                            <span class="fw-bold">Operator Helm Repository:</span>
                            {operatorHelmRepoPackage.version}
                        </li>
                    {/if}
                    {#if upgradedPackage}
                        <li>
                            <span class="fw-bold">Upgraded scylla version:</span>
                            {upgradedPackage?.version}-{upgradedPackage?.date}.{upgradedPackage?.revision_id}
                        </li>
                        {#if upgradedPackage?.build_id}
                            <li>
                               <span class="fw-bold">Build id:</span>
                               {upgradedPackage?.build_id}
                            </li>
                        {/if}
                    {/if}
                {/if}
                <li>
                    <span class="fw-bold">Instance type:</span>
                    {test_run.cloud_setup?.db_node?.instance_type ?? "Unknown"}
                </li>
                <li>
                    <span class="fw-bold">Node amount:</span>
                    {test_run.cloud_setup?.db_node?.node_amount ?? "Unknown"}
                </li>
            </ul>
        </div>
    </div>
    <div class="row">
        <div class="col-12 p-2">
            {#if InProgressStatuses.includes(test_run.status)}
                {#if test_run.sct_runner_host}
                    <div class="mb-1">
                        <div class="input-group">
                            <span class="input-group-text fw-bold">SCT Runner</span>
                            <input
                                type="text"
                                class="form-control user-select-all"
                                disabled
                                value="ssh -i ~/.ssh/scylla_test_id_ed25519 ubuntu@{test_run
                                    .sct_runner_host.public_ip}"
                            />
                            <button
                                class="btn btn-success"
                                type="button"
                                onclick={() => {
                                    navigator.clipboard.writeText(
                                        `ssh -i ~/.ssh/scylla_test_id_ed25519 ubuntu@${test_run.sct_runner_host.public_ip}`
                                    );
                                }}
                            >
                                <Fa icon={faCopy} />
                            </button>
                        </div>
                    </div>
                {/if}
            {/if}
            {#if rebuildRequested}
                <JenkinsBuildModal
                    buildId={test_run.build_id}
                    buildNumber={extractBuildNumber(test_run)}
                    pluginName={test.plugin_name}
                    on:rebuildCancel={() => (rebuildRequested = false)}
                    on:rebuildComplete={() => (rebuildRequested = false)}
                />
            {/if}
            {#if cloneRequested}
                <JenkinsCloneModal
                    buildId={test_run.build_id}
                    buildNumber={extractBuildNumber(test_run)}
                    pluginName={test.plugin_name}
                    testId={test.id}
                    releaseId={release.id}
                    groupId={group.id}
                    oldTestName={test.name}
                    on:cloneCancel={() => (cloneRequested = false)}
                    on:cloneComplete={(e) => {cloneRequested = false; dispatch("cloneComplete", { testId: e.detail.testId }); }}
                />
            {/if}
            <div class="btn-group">
                {#if locateGrafanaNode()}
                    <a
                        target="_blank"
                        href="http://{locateGrafanaNode().instance_info
                        .public_ip}:3000/"
                        class="btn btn-outline-warning">Open Grafana</a
                    >
                {/if}
                {#if !InProgressStatuses.includes(test_run.status)}
                    <a
                        href="https://jenkins.scylladb.com/view/QA/job/QA-tools/job/hydra-show-monitor/parambuild/?test_id={test_run.id}"
                        class="btn btn-outline-primary"
                        target="_blank"
                        aria-current="page"
                        ><Fa icon={faSearch} /> Restore Monitoring Stack</a
                    >
                    <button class="btn btn-sm btn-outline-primary" onclick={() => (rebuildRequested = true)}
                        ><Fa icon={faPlay} /> Rebuild</button
                    >
                    <button class="btn btn-sm btn-outline-primary" onclick={() => (cloneRequested = true)}
                        ><Fa icon={faCopy} /> Clone</button
                    >
                    {#if navigator.clipboard}
                        <button
                            type="button"
                            class="btn btn-outline-success"
                            onclick={() => {
                                navigator.clipboard.writeText(
                                    cmd_hydraInvestigateShowMonitor
                                );
                                sendMessage("success", `\`${cmd_hydraInvestigateShowMonitor}\` has been copied to your clipboard`);
                            }}><Fa icon={faCopy} /> Hydra Show Monitor</button
                        >
                        <button
                            type="button"
                            class="btn btn-outline-success"
                            onclick={() => {
                                navigator.clipboard.writeText(
                                    cmd_hydraInvestigateShowLogs
                                );
                                sendMessage("success", `\`${cmd_hydraInvestigateShowLogs}\` has been copied to your clipboard`);
                            }}><Fa icon={faCopy} /> Hydra Show Logs</button
                        >
                    {/if}
                {/if}
                <a
                    href="/dashboard/{release.name}"
                    class="btn btn-outline-success"
                    ><Fa icon={faBusinessTime} /> Release Dashboard</a
                >
            </div>
        </div>
        {#if !navigator.clipboard}
        <div class="d-flex flex-column p-2">
            <div class="input-group mb-2">
                <span class="input-group-text fw-bold">Show logs</span>
                <input
                    type="text"
                    class="form-control user-select-all"
                    disabled
                    value={cmd_hydraInvestigateShowLogs}
                />
            </div>
            <div class="input-group mb-2">
                <span class="input-group-text fw-bold">Show monitor</span>
                <input
                    type="text"
                    class="form-control user-select-all"
                    disabled
                    value={cmd_hydraInvestigateShowMonitor}
                />
            </div>
        </div>
    {/if}
    </div>
</div>
