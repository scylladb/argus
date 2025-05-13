<script>
    import GithubIssues from "../Github/GithubIssues.svelte";

    export let runId;
    export let testInfo;
</script>

<GithubIssues {runId} id={runId} testId={testInfo.test.id} pluginName={testInfo.test.plugin_name}/>
<div class="accordion accordion-flush border-top" id="allIssuesContainer-{testInfo.test.id}-{runId}">
    <div class="accordion-item">
        <h2 class="accordion-header">
        <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#allIssues-{testInfo.test.id}-{runId}">
            All issues for this test
        </button>
        </h2>
        <div id="allIssues-{testInfo.test.id}-{runId}" class="accordion-collapse collapse" data-bs-parent="#allIssuesContainer-{testInfo.test.id}-{runId}">
        <div class="accordion-body overflow-scroll" style="max-height: 768px">
            <GithubIssues {runId} id={testInfo.test.id} testId={testInfo.test.id} filter_key="test_id" aggregateByIssue={true} submitDisabled={true}/>
        </div>
        </div>
    </div>
</div>
