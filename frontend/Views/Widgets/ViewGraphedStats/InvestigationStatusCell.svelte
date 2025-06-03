<script lang="ts">
    import {
        InvestigationBackgroundCSSClassMap,
        TestInvestigationStatusStrings
    } from "../../../Common/TestStatus";
    import type { TestRun } from "./Interfaces";

    export let run: TestRun;

    const status = run.investigation_status;
    const statusText = TestInvestigationStatusStrings[status as keyof typeof TestInvestigationStatusStrings] || status;
    const badgeClass = InvestigationBackgroundCSSClassMap[status as keyof typeof InvestigationBackgroundCSSClassMap] || "bg-secondary";
</script>

<span
    class="badge {badgeClass} investigation-status-badge"
    title={statusText}
>
    <span class="visually-hidden">{statusText}</span>
</span>

<style>
    .investigation-status-badge {
        width: 40px;
        height: 12px;
        border-radius: 10%;
        display: inline-block;
        cursor: help;
    }
</style>
