<script lang="ts">
    import queryString from "query-string";
    import ReleaseStats from "../Stats/ReleaseStats.svelte";
    import ReleaseActivity from "./ReleaseActivity.svelte";
    import GithubIssues from "../Github/GithubIssues.svelte";
    import TestPopoutSelector from "./TestPopoutSelector.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import TestDashboard from "./TestDashboard.svelte";
    import { TestStatus } from "../Common/TestStatus";
    let { releaseData = {} } = $props();
    let clickedTests = $state({});
    let issuesClicked = $state(false);
    let productVersion = $state(queryString.parse(document.location.search)?.productVersion);
    let stats = $state();

    const handleTestClick = function (detail) {
        if (detail.start_time == 0) {
            sendMessage("info", `The test "${detail.name}" hasn't been run yet!"`, "ReleaseDashboard::testClick");
            return;
        }
        let key = detail.id;
        if (!clickedTests[key]) {
            clickedTests[key] = detail;
        } else {
            delete clickedTests[key];
            clickedTests = clickedTests;
        }
    };

    const handleVersionChange = function (e) {
        productVersion = e.detail.version;
    };

    const handleDeleteRequest = function(e) {
        let key = e.detail.id;
        if (clickedTests[key]) {
            delete clickedTests[key];
            clickedTests = clickedTests;
        }
    };

    const handleQuickSelect = function (e) {
        let tests = e.detail.tests ?? [];
        const detailGroups = e.detail.groups ?? {};
        tests.forEach((v) => {
            const groupStats = detailGroups[v.test.group_id] ?? stats?.groups?.[v.test.group_id];
            const groupName = groupStats?.group?.name ?? v.test.group?.name ?? v.test.group_id ?? "Unknown group";
            handleTestClick({
                name: v.test.name,
                id: v.test.id,
                assignees: [],
                group: groupName,
                status: v.status,
                start_time: v.start_time,
                last_runs: v.last_runs,
                build_system_id: v.test.build_system_id,
            });
        });
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
                            onclick={() => issuesClicked = true}
                        >
                            All Issues
                        </button>
                    </h2>
                    <div
                        id="collapseIssues"
                        class="accordion-collapse collapse bg-light-one"
                    >
                        <div class="accordion-body">
                            {#if issuesClicked}
                            <GithubIssues
                                id={releaseData.release.id}
                                filter_key="release_id"
                                submitDisabled={true}
                                aggregateByIssue={true}
                            />
                            {/if}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <div class="row mb-2">
        <div class="col">
            <ReleaseStats
                horizontal={false}
                displayExtendedStats={true}
                hiddenStatuses={[TestStatus.NOT_PLANNED, TestStatus.NOT_RUN]}
                releaseStats={stats}
                on:quickSelect={handleQuickSelect}
            />
        </div>
    </div>
    <div class="row mb-2">
        <div class="col-xs-2 col-sm-6 col-md-7">
            <TestDashboard
                dashboardObject={releaseData.release}
                {productVersion}
                bind:clickedTests={clickedTests}
                on:testClick={(e) => handleTestClick(e.detail)}
                on:versionChange={handleVersionChange}
                on:statsUpdate={(e) => (stats = e.detail)}
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
