<script lang="ts">
    import Fa from "svelte-fa";
    import { StatusBackgroundCSSClassMap, TestStatus } from "../Common/TestStatus";
    import { subUnderscores, titleCase } from "../Common/TextUtils";
    import { PlannedTest } from "./PlannedJobs.svelte";
    import { faChevronDown, faChevronUp, faHammer } from "@fortawesome/free-solid-svg-icons";
    import TestRuns from "../WorkArea/TestRuns.svelte";
    import { timestampToISODate } from "../Common/DateUtils";

    interface Props {
        test: PlannedTest;
    }

    let { test }: Props = $props();
    let expanded = $state(false);
    let status = (test?.last_run?.status ?? TestStatus.NOT_RUN) as keyof typeof StatusBackgroundCSSClassMap;
</script>

<div class="rounded bg-white overflow-hidden mb-2 d-flex align-items-center">
    <div class="text-center fw-light p-2 text-light {StatusBackgroundCSSClassMap[status]} me-2" style="width:7%">{subUnderscores(status ?? "Unknown").split(" ").map(v => titleCase(v)).join(" ")}</div>
    <div>
        {test.pretty_name || test.name}
        <div class="text-muted text-sm">
            {test.build_system_id}
        </div>
    </div>
    <div class="me-2 ms-auto text-sm text-muted">
        {#if test.last_run}
            {timestampToISODate(test.last_run.start_time)}
        {/if}
    </div>
    <div class="me-2">
        <a class="btn btn-sm btn-dark" href="{test.build_system_url}" target="_blank">
            <Fa icon={faHammer} />
        </a>
    </div>
    <div class="me-2">
        <button class="btn btn-sm btn-primary" onclick={() => (expanded = !expanded)}>
            <Fa icon={expanded ? faChevronUp : faChevronDown} /></button>
    </div>

</div>
{#if expanded}
    <div class="mb-2 bg-white rounded overflow-hidden">
        <TestRuns
            additionalRuns={[]}
            removableRuns={false}
            testId={test.id}
            tab={""}
        />
    </div>
{/if}


<style>
    .text-sm {
        font-size: 0.75rem;
    }

</style>
