<script>
    import {
        faBusinessTime,
        faSearch,
        faCopy,
    } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import { InProgressStatuses } from "../Common/TestStatus";
    import { timestampToISODate } from "../Common/DateUtils";
    import { getScyllaPackage, getKernelPackage } from "../Common/RunUtils";
    export let test_run = {};

    let cmd_hydraInvestigateShowMonitor = `hydra investigate show-monitor ${test_run.id}`;
    let cmd_hydraInvestigateShowLogs = `hydra investigate show-logs ${test_run.id}`;

    const locateGrafanaNode = function () {
        return test_run.allocated_resources.find((node) => {
            return new RegExp(/\-monitor\-node\-/).test(node.name);
        });
    };

    let scyllaPackage = getScyllaPackage(test_run.packages);
    $: scyllaPackage = getScyllaPackage(test_run.packages);
    let kernelPackage = getKernelPackage(test_run.packages);
    $: kernelPackage = getKernelPackage(test_run.packages);
</script>

<div class="container-fluid">
    <div class="row">
        <div class="col-6 p-2">
            <h5>Run Details</h5>
            <ul class="list-unstyled border-start ps-2">
                <li>
                    <span class="fw-bold">Release:</span>
                    {test_run.release_name}
                </li>
                <li>
                    <span class="fw-bold">Group:</span>
                    {test_run.group}
                </li>
                <li>
                    <span class="fw-bold">Test:</span>
                    {test_run.name}
                </li>
                <li>
                    <span class="fw-bold">Id:</span>
                    {test_run.id}
                </li>
                <li>
                    <span class="fw-bold">Start Time:</span>
                    {timestampToISODate(test_run.start_time * 1000, true)}
                </li>
                {#if test_run.end_time != -1}
                    <li>
                        <span class="fw-bold">End Time:</span>
                        {timestampToISODate(test_run.end_time * 1000, true)}
                    </li>
                {/if}
                <li>
                    <span class="fw-bold">Started by:</span>
                    {test_run.started_by ?? "Unknown, probably jenkins"}
                </li>
                <li>
                    <span class="fw-bold">Build Job:</span>
                    <a href={test_run.build_job_url} target="_blank">
                        {test_run.build_job_name}
                    </a>
                </li>
            </ul>
        </div>
        <div class="col-6 p-2">
            <h5>System Information</h5>
            <ul class="list-unstyled border-start ps-2">
                <li>
                    <span class="fw-bold">Backend:</span>
                    {test_run.cloud_setup.backend}
                </li>
                <li>
                    <span class="fw-bold">Region:</span>
                    {test_run.region_name.join(", ")}
                </li>
                <li>
                    <span class="fw-bold">AMI ImageId:</span>
                    {test_run.cloud_setup.db_node.image_id}
                </li>
                <!-- Scylla v4.5.3-0.20211223.c8f14886d (ami-0df0fbe3daf5ad63d) -->
                {#if test_run.packages}
                    {#if kernelPackage}
                        <li>
                            <span class="fw-bold">Kernel Version:</span>
                            {kernelPackage.version}
                        </li>
                    {/if}
                    {#if scyllaPackage}
                        <li>
                            <span class="fw-bold">Scylla Version:</span>
                            {scyllaPackage?.version}-{scyllaPackage?.date}.{scyllaPackage?.revision_id}
                        </li>
                        {#if scyllaPackage?.build_id}
                            <li>
                                <span class="fw-bold">Build Id:</span>
                                {scyllaPackage?.build_id}
                            </li>
                        {/if}
                    {/if}
                {/if}
                <li>
                    <span class="fw-bold">Instance Type:</span>
                    {test_run.cloud_setup.db_node.instance_type}
                </li>
                <li>
                    <span class="fw-bold">Node Amount:</span>
                    {test_run.cloud_setup.db_node.node_amount}
                </li>
            </ul>
        </div>
    </div>
    <div class="row">
        <div class="col-6 p-2">
            {#if InProgressStatuses.includes(test_run.status)}
                <div class="mb-1">
                    <div class="input-group">
                        <span class="input-group-text fw-bold">SCT Runner</span>
                        <input
                            type="text"
                            class="form-control user-select-all"
                            disabled
                            value="ssh -i ~/.ssh/scylla-qa-ec2 ubuntu@{test_run
                                .sct_runner_host.public_ip}"
                        />
                        <button
                            class="btn btn-success"
                            type="button"
                            on:click={() => {
                                navigator.clipboard.writeText(
                                    `ssh -i ~/.ssh/scylla-qa-ec2 ubuntu@${test_run.sct_runner_host.public_ip}`
                                );
                            }}
                        >
                            <Fa icon={faCopy} />
                        </button>
                    </div>
                </div>
            {/if}
            <div class="btn-group">
                {#if InProgressStatuses.includes(test_run.status) && locateGrafanaNode()}
                    <a
                        target="_blank"
                        href="http://{locateGrafanaNode().instance_info
                            .public_ip}:3000/"
                        class="btn btn-outline-warning">Open Grafana</a
                    >
                {:else}
                    <a
                        href="https://jenkins.scylladb.com/view/QA/job/QA-tools/job/hydra-show-monitor/parambuild/?test_id={test_run.id}"
                        class="btn btn-outline-primary"
                        target="_blank"
                        aria-current="page"
                        ><Fa icon={faSearch} /> Restore Monitoring Stack</a
                    >
                    <button
                        type="button"
                        class="btn btn-outline-success"
                        on:click={() => {
                            navigator.clipboard.writeText(
                                cmd_hydraInvestigateShowMonitor
                            );
                        }}><Fa icon={faCopy} /> Hydra Show Monitor</button
                    >
                    <button
                        type="button"
                        class="btn btn-outline-success"
                        on:click={() => {
                            navigator.clipboard.writeText(
                                cmd_hydraInvestigateShowLogs
                            );
                        }}><Fa icon={faCopy} /> Hydra Show Logs</button
                    >
                {/if}
                <a
                    target="_blank"
                    href="/dashboard/{test_run.release_name}"
                    class="btn btn-outline-success"
                    ><Fa icon={faBusinessTime} /> Release Dashboard</a
                >
            </div>
        </div>
    </div>
</div>
