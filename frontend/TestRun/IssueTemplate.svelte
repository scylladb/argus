<script lang="ts">
    import { run } from 'svelte/legacy';

    import Fa from "svelte-fa";
    import { faCopy } from "@fortawesome/free-solid-svg-icons";
    import { parse } from "marked";
    import { onMount } from "svelte";
    import { getScyllaPackage, getKernelPackage, getUpgradedScyllaPackage, getRelocatableScyllaPackage,
        getOperatorPackage, getOperatorHelmPackage, getOperatorHelmRepoPackage,
    } from "../Common/RunUtils";
    import { markdownRendererOptions } from "../markdownOptions";
    import { sendMessage } from "../Stores/AlertStore";
    let { test_run = {}, test } = $props();
    let renderedElement = $state();
    let renderedShortElement = $state();
    let templateElement = $state();
    let shortTemplateElement = $state();
    let issueTemplateText = "";

    const filterDbNodes = function (resources) {
        return resources.filter((val) =>
            new RegExp(/-db-node/).test(val.name)
        );
    };

    const proxyS3Url = function (test, testRun, logName) {
        return `/api/v1/tests/${test.plugin_name}/${testRun.id}/log/${logName}/download`;
    };

    const copyTemplateToClipboard = function () {
        navigator.clipboard.writeText(templateElement.innerText);
        sendMessage("success", "Issue template has been copied to your clipboard");
    };

    const copyShortTemplateToClipboard = function () {
        navigator.clipboard.writeText(shortTemplateElement.innerText);
        sendMessage("success", "Issue template has been copied to your clipboard");
    };


    let scyllaServerPackage = $state(getScyllaPackage(test_run.packages));
    let kernelPackage = $state(getKernelPackage(test_run.packages));
    let relocatablePackage = $state(getRelocatableScyllaPackage(test_run.packages));
    let upgradedPackage = $state(getUpgradedScyllaPackage(test_run.packages));
    run(() => {
        scyllaServerPackage = getScyllaPackage(test_run.packages);
    });
    run(() => {
        kernelPackage = getKernelPackage(test_run.packages);
    });
    run(() => {
        relocatablePackage = getRelocatableScyllaPackage(test_run.packages);
    });
    run(() => {
        upgradedPackage = getUpgradedScyllaPackage(test_run.packages);
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

    onMount(() => {
        renderedElement.innerHTML = parse(templateElement.innerHTML, markdownRendererOptions);
        renderedShortElement.innerHTML = parse(shortTemplateElement.innerHTML, markdownRendererOptions);
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
                    onclick={copyShortTemplateToClipboard}
                    ><Fa icon={faCopy} /> Short</button
                >
                <button
                    type="button"
                    class="btn btn-input-group btn-success"
                    onclick={copyTemplateToClipboard}
                    ><Fa icon={faCopy} /> Full</button
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
                        <li class="nav-item" role="presentation">
                            <button
                                class="nav-link"
                                id="home-tab"
                                data-bs-toggle="tab"
                                data-bs-target="#issueShortTemplateRaw-{test_run.id}"
                                type="button"
                                role="tab"
                            >
                                Short Template
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button
                                class="nav-link"
                                id="profile-tab"
                                data-bs-toggle="tab"
                                data-bs-target="#issueShortTemplatePreview-{test_run.id}"
                                type="button"
                                role="tab"
                            >
                                Preview for Short Template
                            </button>
                        </li>
                    </ul>
                    <div class="tab-content border-start border-end border-bottom p-1">
                        <div
                            class="tab-pane fade show active"
                            id="issueTemplateRaw-{test_run.id}"
                            role="tabpanel"
                        >
                            <div class="p-1 mb-2">
                                <button
                                    class="btn btn-sm btn-primary"
                                    onclick={() => {
                                        let range = document.createRange();
                                        range.selectNodeContents(templateElement);
                                        let selection = window.getSelection();
                                        selection.removeAllRanges();
                                        selection.addRange(range);
                                    }}
                                >
                                    Select All
                                </button>
                            </div>
                            <pre
                                class="code"
                                bind:this={templateElement}
                                id="issueTemplateText-{test_run.id}">
## Packages

{#if scyllaServerPackage}{upgradedPackage ? "Base " : ""}Scylla version: `{scyllaServerPackage.version}-{scyllaServerPackage.date}.{scyllaServerPackage.revision_id}` with build-id `{scyllaServerPackage.build_id}`{/if}
{#if upgradedPackage}Target Scylla version (or git commit hash): `{upgradedPackage.version}-{upgradedPackage.date}.{upgradedPackage.revision_id}` with build-id `{upgradedPackage.build_id}`{/if}
{#if relocatablePackage}Relocatable Package: `{relocatablePackage.version}`{/if}
{#if operatorPackage}Operator Image: `{operatorPackage.version}`{/if}
{#if operatorHelmPackage}Operator Helm Version: `{operatorHelmPackage.version}`{/if}
{#if operatorHelmRepoPackage}Operator Helm Repository: `{operatorHelmRepoPackage.version}`{/if}
{#if kernelPackage}Kernel Version: `{kernelPackage.version}`{/if}


## Issue description

- [ ] This issue is a regression.
- [ ] It is unknown if this issue is a regression.

*Describe your issue in detail and steps it took to produce it.*

## Impact

*Describe the impact this issue causes to the user.*

## How frequently does it reproduce?

*Describe the frequency with how this issue can be reproduced.*

## Installation details

Cluster size: {test_run?.cloud_setup?.db_node?.node_amount ?? "Unknown amount of"} nodes ({test_run?.cloud_setup?.db_node?.instance_type ?? "Unknown instance type"})

Scylla Nodes used in this run:
{#each filterDbNodes(test_run.allocated_resources) as resource}
- {resource.name} ({resource.instance_info.public_ip} | {resource.instance_info.private_ip}) (shards: {resource.instance_info.shards_amount}){"\n"}
{:else}
**No resources left at the end of the run**
{/each}

OS / Image: `{test_run?.cloud_setup?.db_node?.image_id ?? "No image"}` ({test_run?.sct_runner_host?.provider ?? "NO RUNNER"}: {test_run?.sct_runner_host?.region ?? "NO RUNNER"})

Test: `{test?.name}`
Test id: `{test_run.id}`
Test name: `{test_run.build_id}`
{#if test_run.test_method}
Test method: `{test_run.test_method}`
{/if}
Test config file(s):

- [{(test_run.config_files?.[0] ?? "None").split("/").reverse()[0]}](https://github.com/scylladb/scylla-cluster-tests/blob/{test_run.scm_revision_id}/{test_run.config_files[0]})


&lt;details&gt;
&lt;summary&gt;
Logs and commands
&lt;/summary&gt;


- Restore Monitor Stack command: `$ hydra investigate show-monitor {test_run.id}`
- Restore monitor on AWS instance using [Jenkins job](https://jenkins.scylladb.com/view/QA/job/QA-tools/job/hydra-show-monitor/parambuild/?test_id={test_run.id})
- Show all stored logs command: `$ hydra investigate show-logs {test_run.id}`


## Logs:
{#each test_run.logs as log}
- **[{log[0]}](https://argus.scylladb.com{proxyS3Url(test, test_run, log[0])})**{"\n"}
{:else}
*No logs captured during this run.*
{/each}

[Jenkins job URL]({test_run.build_job_url})
[Argus]({document.location.origin}/test/{test_run.test_id}/runs?additionalRuns[]={test_run.id})
&lt;/details&gt;

                            </pre>
                        </div>
                        <div class="tab-pane fade" id="issueTemplatePreview-{test_run.id}" role="tabpanel">
                            <div
                                class="p-2 markdown-body"
                                bind:this={renderedElement}
                                id="issueTemplateRendered-{test_run.id}"
></div>
                        </div>
                        <div
                            class="tab-pane fade"
                            id="issueShortTemplateRaw-{test_run.id}"
                            role="tabpanel"
                        >
                            <div class="p-1 mb-2">
                                <button
                                    class="btn btn-sm btn-primary"
                                    onclick={() => {
                                        let range = document.createRange();
                                        range.selectNodeContents(shortTemplateElement);
                                        let selection = window.getSelection();
                                        selection.removeAllRanges();
                                        selection.addRange(range);
                                    }}
                                >
                                    Select All
                                </button>
                            </div>
                            <pre
                                class="code"
                                bind:this={shortTemplateElement}
                                id="issueShortTemplateText-{test_run.id}">

[Argus]({document.location.origin}/test/{test_run.test_id}/runs?additionalRuns[]={test_run.id})

{#if scyllaServerPackage}{upgradedPackage ? "Base " : ""}Scylla version: `{scyllaServerPackage.version}-{scyllaServerPackage.date}.{scyllaServerPackage.revision_id}` with build-id `{scyllaServerPackage.build_id}`{/if}
{#if upgradedPackage}Target Scylla version (or git commit hash): `{upgradedPackage.version}-{upgradedPackage.date}.{upgradedPackage.revision_id}` with build-id `{upgradedPackage.build_id}`{/if}
{#if relocatablePackage}Relocatable Package: `{relocatablePackage.version}`{/if}
{#if operatorPackage}Operator Image: `{operatorPackage.version}`{/if}
{#if operatorHelmPackage}Operator Helm Version: `{operatorHelmPackage.version}`{/if}
{#if operatorHelmRepoPackage}Operator Helm Repository: `{operatorHelmRepoPackage.version}`{/if}
{#if kernelPackage}Kernel Version: `{kernelPackage.version}`{/if}

&lt;details&gt;
&lt;summary&gt;
Extra information
&lt;/summary&gt;

## Installation details

Cluster size: {test_run?.cloud_setup?.db_node?.node_amount ?? "Unknown amount of"} nodes ({test_run?.cloud_setup?.db_node?.instance_type ?? "Unknown instance type"})

Scylla Nodes used in this run:
{#each filterDbNodes(test_run.allocated_resources) as resource}
    - {resource.name} ({resource.instance_info.public_ip} | {resource.instance_info.private_ip}) (shards: {resource.instance_info.shards_amount}){"\n"}
{:else}
    **No resources left at the end of the run**
{/each}

OS / Image: `{test_run?.cloud_setup?.db_node?.image_id ?? "No image"}` ({test_run?.sct_runner_host?.provider ?? "NO RUNNER"}: {test_run?.sct_runner_host?.region ?? "NO RUNNER"})

Test: `{test?.name}`
Test id: `{test_run.id}`
Test name: `{test_run.build_id}`
{#if test_run.test_method}
Test method: `{test_run.test_method}`
{/if}
Test config file(s):

- [{(test_run.config_files?.[0] ?? "None").split("/").reverse()[0]}](https://github.com/scylladb/scylla-cluster-tests/blob/{test_run.scm_revision_id}/{test_run.config_files[0]})


## Logs:
{#each test_run.logs as log}
- **[{log[0]}](https://argus.scylladb.com{proxyS3Url(test, test_run, log[0])})**{"\n"}
{:else}
*No logs captured during this run.*
{/each}
[Jenkins job URL]({test_run.build_job_url})
&lt;/details&gt;

                            </pre>
                        </div>
                        <div class="tab-pane fade" id="issueShortTemplatePreview-{test_run.id}" role="tabpanel">
                            <div
                                class="p-2 markdown-body"
                                bind:this={renderedShortElement}
                                id="issueTemplateRendered-{test_run.id}"
></div>
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
