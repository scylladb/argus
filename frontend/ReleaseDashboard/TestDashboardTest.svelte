<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import { InvestigationStatusIcon, StatusBackgroundCSSClassMap, TestInvestigationStatus, TestInvestigationStatusStrings, TestStatus } from "../Common/TestStatus";
    import { subUnderscores, titleCase } from "../Common/TextUtils";
    import AssigneeList from "../WorkArea/AssigneeList.svelte";
    import humanizeDuration from "humanize-duration";
    import { timestampToISODate } from "../Common/DateUtils";
    import Fa from "svelte-fa";
    import { faBug, faComment, faSpider } from "@fortawesome/free-solid-svg-icons";
    import { getAssigneesForTest, shouldFilterOutByUser } from "./TestDashboard.svelte";

    let {
        testStats,
        groupStats,
        assigneeList,
        clickedTests,
        doFilters
    } = $props();

    let lastRun = testStats?.last_runs?.[0];
    const dispatch = createEventDispatcher();
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
    role="button"
    tabindex="-1"
    class:d-none={!doFilters(testStats)}
    class:status-block-active={testStats.start_time != 0}
    class:investigating={testStats?.investigation_status == TestInvestigationStatus.IN_PROGRESS}
    class:should-be-investigated={testStats?.investigation_status == TestInvestigationStatus.NOT_INVESTIGATED && [TestStatus.FAILED, TestStatus.TEST_ERROR].includes(testStats?.status)}
    class="rounded bg-main status-block m-1 d-flex flex-column overflow-hidden shadow-sm"
    onclick={() => {
        dispatch("testClick", { testStats, groupStats });
    }}
>
    <div
        class="{StatusBackgroundCSSClassMap[
            testStats.status as keyof typeof StatusBackgroundCSSClassMap
        ]} text-center text-light p-1 border-bottom"
    >
        {testStats.status == "unknown"
            ? "Not run"
            : subUnderscores(testStats.status ?? "Unknown").split(" ").map(v => titleCase(v)).join(" ")}
        {#if clickedTests[testStats.test.id]}
            <div class="text-tiny">Selected</div>
        {/if}
    </div>
    <div class="p-1 text-small d-flex align-items-center">
        <div class="ms-1">{testStats.test.name}
        {#if testStats.buildNumber}
            - <span class="fw-bold">#{testStats.buildNumber}</span> <span class="text-muted">({timestampToISODate(testStats.start_time).split(" ")[0]})</span>
        {/if}
        </div>
    </div>
    <div class="d-flex flex-fill align-items-end justify-content-end p-1">
        <div class="p-1 me-auto text-small">
            {#if (lastRun?.nemesis_data ?? []).length}
                <Fa icon={faSpider} /> {(lastRun?.nemesis_data ?? []).filter((n: {status: string}) => n.status == "failed").length} / {(lastRun?.nemesis_data ?? []).length}
            {/if}
        </div>
        <div class="p-1 me-2">
            {#if assigneeList.tests[testStats.test.id] || assigneeList.groups[groupStats.group.id] || testStats.last_runs?.[0]?.assignee}
                <AssigneeList
                    smallImage={false}
                    assignees={getAssigneesForTest(
                        assigneeList,
                        testStats.test.id,
                        groupStats.group.id,
                        testStats.last_runs ?? [],
                    )}
                />
            {/if}
        </div>
        {#if testStats.investigation_status && (testStats.status != TestStatus.PASSED || testStats.investigation_status != TestInvestigationStatus.NOT_INVESTIGATED)}
            <div
                class="p-1"
                title="Investigation: {TestInvestigationStatusStrings[
                    testStats.investigation_status as keyof typeof TestInvestigationStatusStrings
                ]}"
            >
                <Fa
                    color="#000"
                    icon={InvestigationStatusIcon[
                        testStats.investigation_status as keyof typeof InvestigationStatusIcon
                    ]}
                />
            </div>
        {/if}
        {#if testStats.hasBugReport}
            <div class="p-1" title="Has a bug report">
                <Fa color="#000" icon={faBug} />
            </div>
        {/if}
        {#if testStats.hasComments}
            <div class="p-1" title="Has a comment">
                <Fa color="#000" icon={faComment} />
            </div>
        {/if}
    </div>
    {#if lastRun?.end_time && new Date(lastRun.end_time).getTime() > 1}
        <div class="border-top bg-light-two text-small text-center">
            took {humanizeDuration((new Date(lastRun.end_time).getTime() - new Date(lastRun.start_time).getTime()), { units: ["d", "h", "m"], largest: 1, round: true })}
        </div>
    {/if}
</div>


<style>
    .status-block {
        width: 178px;
        max-height: 220px;
        box-sizing: border-box;
        cursor: pointer;
    }

    .img-thumb {
        border-radius: 50%;
        width: 32px;
    }

    .text-small {
        font-size: 0.8em;
    }

    .text-tiny {
        font-size: 0.6em;
    }

    .should-be-investigated {
        border: 3px solid #dc3545 !important;
    }

    .investigating {
        border: 3px solid #ff9036 !important;
    }
</style>
