<script>
    export let releaseData = {};
    import ReleaseStats from "../Stats/ReleaseStats.svelte";
    import ReleaseActivity from "./ReleaseActivity.svelte";
    import GithubIssues from "../Github/GithubIssues.svelte";
    import TestPopoutSelector from "./TestPopoutSelector.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    let clickedTests = {};

    const handleTestClick = function (e) {
        if (e.detail.start_time == 0) {
            sendMessage("info", `The test "${e.detail.name}" hasn't been run yet!"`);
            return;
        }
        let key = `${e.detail.group}/${e.detail.name}`;
        if (!clickedTests[key]) {
            clickedTests[key] = e.detail;
        } else {
            delete clickedTests[key];
            clickedTests = clickedTests;
        }
    };

    const handleDeleteRequest = function(e) {
        let key = `${e.detail.group}/${e.detail.name}`;
        if (clickedTests[key]) {
            delete clickedTests[key];
            clickedTests = clickedTests;
        }
    };
</script>

<div class="container-fluid border rounded mt-1 bg-white shadow-sm">
    <div class="row mb-2">
        <div class="col-8">
            <h1 class="display-1">{releaseData.release.name}</h1>
        </div>
    </div>
    <div class="row mb-2">
        <div class="col">
            <div class="accordion">
                <div class="accordion-item">
                    <h2 class="accordion-header">
                        <button
                            class="accordion-button collapsed"
                            type="button"
                            data-bs-toggle="collapse"
                            data-bs-target="#collapseIssues"
                        >
                            All Issues
                        </button>
                    </h2>
                    <div
                        id="collapseIssues"
                        class="accordion-collapse collapse bg-light-one"
                    >
                        <div class="accordion-body">
                            <GithubIssues
                                id={releaseData.release.id}
                                filter_key="release_id"
                                submitDisabled={true}
                                aggregateByIssue={true}
                            />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <div class="row mb-2">
        <div class="col-xs-2 col-sm-6 col-md-7">
            <ReleaseStats
                releaseName={releaseData.release.name}
                releaseId={releaseData.release.id}
                showTestMap={true}
                horizontal={false}
                bind:clickedTests={clickedTests}
                on:testClick={handleTestClick}
            />
        </div>
        <div class="col-xs-10 col-sm-6 col-md-5">
            <TestPopoutSelector
                bind:tests={clickedTests}
                on:deleteRequest={handleDeleteRequest}
                releaseName={releaseData.release.name}
            />
        </div>
    </div>
    <div class="row mb-2">
        <ReleaseActivity releaseName={releaseData.release.name} />
    </div>
</div>
