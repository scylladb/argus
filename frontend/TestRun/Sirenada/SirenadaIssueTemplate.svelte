<script lang="ts">
    import Fa from "svelte-fa";
    import { faCopy } from "@fortawesome/free-solid-svg-icons";
    import { parse } from "marked";
    import { onMount } from "svelte";
    import { markdownRendererOptions } from "../../markdownOptions";
    let { test_run = {} } = $props();
    let renderedElement = $state();
    let templateElement = $state();
    let issueTemplateText = "";


    const copyTemplateToClipboard = function () {
        navigator.clipboard.writeText(templateElement.innerText);
    };

    onMount(() => {
        renderedElement.innerHTML = parse(templateElement.innerHTML, markdownRendererOptions);
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
                    Cloud issue template
                </button>
                <button
                    type="button"
                    class="btn btn-input-group btn-success"
                    onclick={copyTemplateToClipboard}
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
### What environment are you running on?

- [ ] Lab
- [ ] AppQA
- [ ] Staging
- [ ] Production
- [ ] Local

<!-- You may add any other details about the environment, like the backend version -->

### What is the cluster cloud provider?

- [ ] AWS
- [ ] GCP
- [ ] Serverless

### Does the issue always reproduce?

- [ ] Yes
- [ ] No
- [ ] I don't know

### What steps will reproduce the problem?

1.
2.

### What is the expected result?

...

### What happens instead?

...

### Additional information

[Jenkins job URL]({test_run.build_job_url})
[Argus]({document.location.origin}/test/{test_run.test_id}/runs?additionalRuns[]={test_run.id})

<!-- cluster ID / logs / trace ID / version / suspected regression / comments -->

                            </pre>
                        </div>
                        <div class="tab-pane fade" id="issueTemplatePreview-{test_run.id}" role="tabpanel">
                            <div
                                class="p-2 markdown-body"
                                bind:this={renderedElement}
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
