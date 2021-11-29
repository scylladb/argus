<script>
    export let test_run = {};
    import { parse } from "marked";
    import { onMount } from "svelte";
    let renderedElement;
    let templateElement;
    let issueTemplateText = "";

    const findScyllaServerPackage = function() {
        let filtered_packages = test_run.packages.filter((val) => {
            if (val.name == "scylla-server") {
                return val;
            }
        });
        return filtered_packages.length > 0 ? filtered_packages[0] : {
            "name": "scylla-server",
            "date": "19700101",
            "revision_id": "000000000000",
            "version": "not found"
        };
    }

    const copyTemplateToClipboard = function() {
        navigator.clipboard.writeText(issueTemplateText);
    }

    let scyllaServerPackage = findScyllaServerPackage();

    onMount(()=>{
        renderedElement.innerHTML = parse(templateElement.innerHTML);
        issueTemplateText = templateElement.innerHTML;
    });
</script>

<div class="accordion accordion-flush" id="accordionIssueTemplate-{test_run.id}">
    <div class="accordion-item">
        <h2 class="accordion-header" id="headingIssueTemplate-{test_run.id}">
            <button
                class="accordion-button collapsed"
                type="button"
                data-bs-toggle="collapse"
                data-bs-target="#collapseIssueTemplate-{test_run.id}"
            >
                Issue template
            </button>
        </h2>
        <div
            id="collapseIssueTemplate-{test_run.id}"
            class="accordion-collapse collapse"
            aria-labelledby="headingOne"
            data-bs-parent="#accordionIssueTemplate-{test_run.id}"
        >
            <div class="accordion-body">
                <div class="text-end">
                    <button type="button" class="btn btn-success" on:click={copyTemplateToClipboard}
                        ><i class="far fa-copy" /></button
                    >
                </div>
                <pre
                    bind:this={templateElement}
                    id="issueTemplateText-{test_run.id}"
                    class="d-none">
## Installation details


Scylla version (or git commit hash): `{scyllaServerPackage.version} with build-id {scyllaServerPackage.revision_id}`

Cluster size: {test_run.cloud_setup.db_node.node_amount} nodes ({test_run.cloud_setup.db_node.instance_type})

Scylla running with shards number (live nodes):
{#each test_run.leftover_resources as resource}
    - {resource.name} ({resource.instance_info.public_ip} | {resource.instance_info.private_ip}){"\n"}
{:else}
    **No resources left at the end of the run**
{/each}

OS (RHEL/CentOS/Ubuntu/AWS AMI): `{test_run.cloud_setup.db_node.image_id}` ({test_run.sct_runner_host.provider}: {test_run.sct_runner_host.region})


Test: `{test_run.name}`

Test id: `{test_run.id}`

Test name: `{test_run.group}/{test_run.name}`

Test config file(s):

- [{test_run.config_files[0].split("/").reverse()[0]}](https://github.com/scylladb/scylla-cluster-tests/blob/{test_run.scm_revision_id}/{test_run.config_files[0]})


## Issue description
#### &gt;&gt;&gt;&gt;&gt;&gt;&gt;

**Your description here...**

#### &lt;&lt;&lt;&lt;&lt;&lt;&lt;

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
                <div
                    bind:this={renderedElement}
                    id="issueTemplateRendered-{test_run.id}"
                />
            </div>
        </div>
    </div>
</div>
