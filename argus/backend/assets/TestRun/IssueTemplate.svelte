<script>
    export let test_run = {};
    import Fa from "svelte-fa";
    import { faCopy } from "@fortawesome/free-solid-svg-icons";
    import { parse } from "marked";
    import { onMount } from "svelte";
    import { getScyllaPackage, getKernelPackage } from "../Common/RunUtils";
    let renderedElement;
    let templateElement;
    let issueTemplateText = "";

    const filterDbNodes = function (resources) {
        return resources.filter((val) =>
            new RegExp(/\-db\-node/).test(val.name)
        );
    };

    const copyTemplateToClipboard = function () {
        navigator.clipboard.writeText(issueTemplateText);
    };

    let scyllaServerPackage = getScyllaPackage(test_run.packages);
    let kernelPackage = getKernelPackage(test_run.packages);
    $: scyllaServerPackage = getScyllaPackage(test_run.packages);
    $: kernelPackage = getKernelPackage(test_run.packages);

    onMount(() => {
        renderedElement.innerHTML = parse(templateElement.innerHTML);
        issueTemplateText = templateElement.innerHTML;
    });
</script>

<div class="container-fluid mb-2">
    <div class="row">
        <div class="col mt-2">
            <div class="input-group">
                <button
                    class="btn btn-input-group btn-primary"
                    type="button"
                    data-bs-toggle="collapse"
                    data-bs-target="#collapseIssueTemplate-{test_run.id}"
                >
                    Scylla Issue Template
                </button>
                <button
                    type="button"
                    class="btn btn-input-group btn-success"
                    on:click={copyTemplateToClipboard}
                    ><Fa icon={faCopy} /></button
                >
            </div>
            <div id="collapseIssueTemplate-{test_run.id}" class="collapse">
                <div class="accordion-body">
                    <ul
                        class="nav nav-tabs"
                        role="tablist"
                        id="issuePreviewTabs-{test_run.id}"
                    >
                        <li class="nav-item" role="presentation">
                            <button
                                class="nav-link active"
                                id="home-tab"
                                data-bs-toggle="tab"
                                data-bs-target="#issueTemplateRaw-{test_run.id}"
                                type="button"
                                role="tab"
                            >
                                Template
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button
                                class="nav-link"
                                id="profile-tab"
                                data-bs-toggle="tab"
                                data-bs-target="#issueTemplatePreview-{test_run.id}"
                                type="button"
                                role="tab"
                            >
                                Preview
                            </button>
                        </li>
                    </ul>
                    <div class="tab-content border-start border-end border-bottom p-1">
                        <div
                            class="tab-pane fade show active"
                            id="issueTemplateRaw-{test_run.id}"
                            role="tabpanel"
                        >
                            <pre
                                class="code user-select-all"
                                bind:this={templateElement}
                                id="issueTemplateText-{test_run.id}">
## Installation details

{#if kernelPackage}
Kernel Version: {kernelPackage.version}
{/if}

{#if scyllaServerPackage}
Scylla version (or git commit hash): `{scyllaServerPackage.version}-{scyllaServerPackage.date}.{scyllaServerPackage.revision_id}` with build-id `{scyllaServerPackage.build_id}`
{/if}

Cluster size: {test_run.cloud_setup.db_node.node_amount} nodes ({test_run.cloud_setup.db_node.instance_type})

Scylla running with shards number (live nodes):
{#each filterDbNodes(test_run.leftover_resources) as resource}
    - {resource.name} ({resource.instance_info.public_ip} | {resource.instance_info.private_ip}) (shards: {resource.instance_info.shards_amount}){"\n"}
{:else}
    **No resources left at the end of the run**
{/each}

OS / Image: `{test_run.cloud_setup.db_node.image_id}` ({test_run.sct_runner_host.provider}: {test_run.sct_runner_host.region})


Test: `{test_run.name}`

Test id: `{test_run.id}`

Test name: `{test_run.group}/{test_run.name}`

Test config file(s):

- [{test_run.config_files[0].split("/").reverse()[0]}](https://github.com/scylladb/scylla-cluster-tests/blob/{test_run.scm_revision_id}/{test_run.config_files[0]})


## Issue description

&gt;&gt;&gt;&gt;&gt;&gt;&gt;

**Your description here...**

&lt;&lt;&lt;&lt;&lt;&lt;&lt;

- Restore Monitor Stack command: `$ hydra investigate show-monitor {test_run.id}`
- Restore monitor on AWS instance using [Jenkins job](https://jenkins.scylladb.com/view/QA/job/QA-tools/job/hydra-show-monitor/parambuild/?test_id={test_run.id})
- Show all stored logs command: `$ hydra investigate show-logs {test_run.id}`



## Logs:
{#each test_run.logs as log}
    - **{log[0]}** - [{log[1]}]({log[1]}){"\n"}
{:else}
    *No logs captured during this run.*
{/each}

[Jenkins job URL]({test_run.build_job_url})
                            </pre>
                        </div>
                        <div class="tab-pane fade" id="issueTemplatePreview-{test_run.id}" role="tabpanel">
                            <div
                                class="p-2 markdown-body"
                                bind:this={renderedElement}
                                id="issueTemplateRendered-{test_run.id}"
                            />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<style>
    .code {
        font-size: 11pt;
        padding: 1em;
        background-color: #f0f0f0;
    }
</style>
