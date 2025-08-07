<script module>
    export const submitIssue = async function (url, runId, testId) {
        try {
            if (!testId) return;
            let apiResponse = await fetch(`/api/v1/test/${testId}/run/${runId}/issues/submit`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    issue_url: url,
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                sendMessage(
                    "success",
                    "Issue has been added to the current run!",
                    "IssueTab::submit"
                );
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error while submitting an issue on a test run.\nMessage: ${error.response.arguments[0]}`,
                    "IssueTab::submit"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during issue submission.",
                    "IssueTab::submit"
                );
            }
        }
    };
</script>

<script lang="ts">
    import GithubIssues from "../Github/GithubIssues.svelte";
    import { sendMessage } from "../Stores/AlertStore";

    let { runId, testInfo } = $props();

    const submitIssueLocal = async function (url, runId, testId) {
        await submitIssue(url, runId, testId);
        runIssuesComponent.fetchIssues();
        aggregatedIssuesComponent.fetchIssues();
    };

    let aggregatedIssuesComponent = $state();
    let runIssuesComponent = $state();

</script>

<GithubIssues bind:this={runIssuesComponent} {runId} id={runId} testId={testInfo.test.id} pluginName={testInfo.test.plugin_name}/>
<div class="accordion accordion-flush border-top" id="allIssuesContainer-{testInfo.test.id}-{runId}">
    <div class="accordion-item">
        <h2 class="accordion-header">
        <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#allIssues-{testInfo.test.id}-{runId}">
            All issues for this test
        </button>
        </h2>
        <div id="allIssues-{testInfo.test.id}-{runId}" class="accordion-collapse collapse" data-bs-parent="#allIssuesContainer-{testInfo.test.id}-{runId}">
        <div class="accordion-body overflow-scroll" style="max-height: 768px">
            <GithubIssues on:submitToCurrent={(e) => submitIssueLocal(e.detail, runId, testInfo.test.id)} bind:this={aggregatedIssuesComponent} {runId} id={testInfo.test.id} testId={testInfo.test.id} filter_key="test_id" aggregateByIssue={true} submitDisabled={true}/>
        </div>
        </div>
    </div>
</div>
