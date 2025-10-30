<script lang="ts">
    import Fa from "svelte-fa";
    import { TestStatus, StatusBackgroundCSSClassMap, TestInvestigationStatus, TestInvestigationStatusStrings, StatusCSSClassMap, InvestigationStatusIcon } from "../Common/TestStatus";
    import { titleCase, subUnderscores } from "../Common/TextUtils";
    import { Collapse } from "bootstrap";
    import { createEventDispatcher } from "svelte";
    import { faChevronRight } from "@fortawesome/free-solid-svg-icons";
    interface Props {
        displayNumber?: boolean;
        displayPercentage?: boolean;
        displayInvestigations?: boolean;
        hiddenStatuses?: any;
        stats?: any;
    }

    let {
        displayNumber = false,
        displayPercentage = false,
        displayInvestigations = false,
        hiddenStatuses = [],
        stats = {
        created: 0,
        running: 0,
        passed: 0,
        failed: 0,
        lastStatus: "unknown",
        total: -1,
    }
    }: Props = $props();

    let shortBlock = $state();
    let extendedBlock = $state();

    const dispatch = createEventDispatcher();
    const normalize = function(val, max, min) {
        return (val - min) / (max - min);
    };

    const toggleExtendedInvestigations = function () {
        new Collapse(shortBlock, { toggle: true });
        new Collapse(extendedBlock, {toggle: true });
    };

    const calcPercentageForStatus = function(status, stats) {
        const allowedStatuses = Object.values(TestStatus).filter(v => !hiddenStatuses.includes(v));
        const filteredTotal = Object
            .entries(stats)
            .filter(v => allowedStatuses.includes(v[0]) && typeof v[1] === "number")
            .reduce((acc, v) => acc + v[1], 0);
        const statusCount = stats?.[status] ?? 0;
        return (statusCount / filteredTotal * 100).toFixed(1);
    };

    const getTestsForStatus = function(stats, investigationStatus, status) {
        let tests = Object
            .values(stats.release ? Object.values(stats.groups).reduce((tests, group) => [...tests, ...Object.values(group.tests)], []) : Object.values(stats.tests))
            .filter(v => v.investigation_status == investigationStatus && v.status == status);
        return tests;
    };

    const calculateStatusStats = function(stats, investigationStatus, allowedStatuses) {
        const statusStats = stats?.[investigationStatus];
        if (!statusStats) return {
            total: 0,
            counts: [],
        };
        const filtered = Object.entries(statusStats)
            .filter(v => allowedStatuses.includes(v[0]) && v[1] > 0);
        const total = filtered.reduce((acc, val) => acc + val[1], 0);
        const statusStatsPerStatus = filtered
            .map(v => [...v, (v[1] / total * 100).toFixed(1)])
            .reduce((acc, v) => {
                acc[v[0]] = {
                    amount: v[1],
                    percentage: v[2],
                };
                return acc;
            }, {});
        return {
            total: total,
            counts: statusStatsPerStatus,
        };
    };
</script>

<div class="d-flex flex-column">
    <div
        class="flex-fill d-flex shadow-sm overflow-hidden border rounded cursor-question"
        title="Total: {stats.total}"
    >
        {#each Object.values(TestStatus) as status}
            {#if stats[status]}
                <div
                    class:d-none={stats[status] == 0}
                    class="d-flex align-items-center justify-content-center flex-fill {StatusBackgroundCSSClassMap[status]}"
                    style="width: {Math.max(Math.round(normalize(stats[status], stats.total, 0) * 100), 10)}%"
                    title="{subUnderscores(titleCase(status))} ({stats[status]})"
                >
                    <div class="p-1 text-small text-light text-center text-outline">
                        {#if displayNumber}
                            {stats[status]}
                        {/if}
                        {#if displayPercentage}
                            {displayNumber ? "(" : ""}{calcPercentageForStatus(status, stats)}%{displayNumber ? ")" : ""}
                        {/if}
                    </div>
                </div>
            {/if}
        {/each}
    </div>
    {#if stats.total != -1 && displayInvestigations}
        {@const allowedStatuses = Object.values(TestStatus).filter(v => !hiddenStatuses.includes(v))}
        <div
            class="mt-2 collapse show"
            bind:this={shortBlock}
        >
            <div
                class="align-self-start d-inline-flex shadow-sm overflow-hidden border rounded cursor-pointer"
                onclick={toggleExtendedInvestigations}
            >
                {#each Object.values(TestInvestigationStatus) as investigationStatus, idx}
                    {@const statusStats = calculateStatusStats(stats, investigationStatus, allowedStatuses)}
                    <div
                        class="flex-fill text-center {idx > 0 ? "border-start" : ""} px-3 py-2"
                        role="button"
                    >
                        <Fa icon={InvestigationStatusIcon[investigationStatus]}/>
                        {statusStats?.total}
                    </div>
                {/each}
            </div>
        </div>
        <div class="collapse mt-2" bind:this={extendedBlock}>
            <div class="d-inline-flex flex-column">
                <div class="d-flex bg-light-one p-2 rounded">
                    {#each Object.values(TestInvestigationStatus) as investigationStatus, idx}
                        {@const statusStats = calculateStatusStats(stats, investigationStatus, allowedStatuses)}
                        <div class="{idx > 0 ? "ms-2" : ""} rounded bg-white">
                            <h6 class="p-2 border-bottom">
                                <Fa icon={InvestigationStatusIcon[investigationStatus]}/>
                                {TestInvestigationStatusStrings[investigationStatus]}
                                <span class="d-inline-block ms-3 text-end">
                                    {statusStats?.total}
                                </span>
                            </h6>
                            <div class="p-2 d-flex flex-column">
                                {#each allowedStatuses as status}
                                    {#if statusStats.counts?.[status]}
                                        <div class="flex-fill d-flex align-items-center">
                                            <div class="me-4">
                                                <button
                                                    class="btn btn-sm btn-light mb-1"
                                                    onclick={() => {
                                                        const groups = stats.groups ?? (stats.group?.id ? { [stats.group.id]: stats } : undefined);
                                                        dispatch("quickSelect", {
                                                            tests: getTestsForStatus(stats, investigationStatus, status),
                                                            groups
                                                        });
                                                    }}
                                                >
                                                    <Fa icon={faChevronRight} />
                                                    {subUnderscores(titleCase(status))}
                                                </button>
                                            </div>
                                            <div class="ms-auto fw-bold {StatusCSSClassMap[status]}">{statusStats.counts[status].amount} ({statusStats.counts[status].percentage}%)</div>
                                        </div>
                                    {/if}
                                {/each}
                            </div>
                        </div>
                    {/each}
                </div>
                <button class="btn btn-dark mt-2" onclick={toggleExtendedInvestigations}>Hide</button>
            </div>
        </div>
    {/if}
</div>
<style>
    .cursor-question {
        cursor: help;
    }

    .cursor-pointer {
        cursor: pointer;
    }

    .text-small {
        font-size: 0.75em;
    }

    .text-outline {
        color: white;
        font-weight: 500;
    }
    .bg-gray {
        background-color: #dddddd;
    }
</style>
