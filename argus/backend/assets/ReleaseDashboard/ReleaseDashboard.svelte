<script>
    export let releaseData = {};
    import { faGithub } from "@fortawesome/free-brands-svg-icons";
    import { faBug } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import ChartStats from "../Stats/ChartStats.svelte";
    import ReleaseStats from "../Stats/ReleaseStats.svelte";
    import ReleaseActivity from "./ReleaseActivity.svelte";
    import GithubIssues from "../Github/GithubIssues.svelte";
    import ReleaseGithubIssues from "./ReleaseGithubIssues.svelte";
    import TestPopoutSelector from "./TestPopoutSelector.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    let clickedTests = {};

    const handleTestClick = function (e) {
        if (e.detail.start_time == 0) {
            sendMessage("info", `The test "${e.detail.name}" hasn't been run yet!"`);
            return;
        }

        if (!clickedTests[e.detail.name]) {
            clickedTests[e.detail.name] = e.detail;
        } else {
            delete clickedTests[e.detail.name];
            clickedTests = clickedTests;
        }
    };

    const handleDeleteRequest = function(ev) {
        if (clickedTests[ev.detail.name]) {
            delete clickedTests[ev.detail.name];
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
        <div class="col-8">
            <ReleaseStats
                releaseName={releaseData.release.name}
                DisplayItem={ChartStats}
                showTestMap={true}
                horizontal={true}
                bind:clickedTests={clickedTests}
                on:testClick={handleTestClick}
            />
        </div>
        <div class="col-4">
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
                        class="accordion-collapse collapse"
                    >
                        <div class="accordion-body">
                            <GithubIssues
                                id={releaseData.release.id}
                                filter_key="release_id"
                                submitDisabled={true}
                            />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
