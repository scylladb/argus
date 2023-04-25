<script>
    import Fa from "svelte-fa";
    import { TestStatus, StatusBackgroundCSSClassMap, TestInvestigationStatus, TestInvestigationStatusStrings, StatusCSSClassMap } from "../Common/TestStatus";
    import { titleCase, subUnderscores } from "../Common/TextUtils";
    import { faEye, faEyeSlash, faSearch } from "@fortawesome/free-solid-svg-icons";
    import { Collapse } from "bootstrap";
    export let displayNumber = false;
    export let displayInvestigations = false;
    export let stats = {
        created: 0,
        running: 0,
        passed: 0,
        failed: 0,
        lastStatus: "unknown",
        total: -1,
    };

    let shortBlock;
    let extendedBlock;

    const investigationStatusMapping = {
        [TestInvestigationStatus.INVESTIGATED]: faEye,
        [TestInvestigationStatus.NOT_INVESTIGATED]: faEyeSlash,
        [TestInvestigationStatus.IN_PROGRESS]: faSearch,
    };

    const normalize = function(val, max, min) {
        return (val - min) / (max - min);
    };

    const toggleExtendedInvestigations = function () {
        new Collapse(shortBlock, { toggle: true });
        new Collapse(extendedBlock, {toggle: true });
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
                    <div class="p-1 text-small text-light text-outline">
                        {#if displayNumber}
                            {stats[status]}
                        {/if}
                    </div>
                </div>
            {/if}
        {/each}
    </div>
    {#if stats.release && displayInvestigations}
        <div 
            class="mt-2 collapse show"
            bind:this={shortBlock}
        >
            <div
                class="align-self-start d-inline-flex shadow-sm overflow-hidden border rounded cursor-pointer"
                on:click={toggleExtendedInvestigations}
            >
                {#each Object.values(TestInvestigationStatus) as investigationStatus, idx}
                    <div 
                        class="flex-fill text-center {idx > 0 ? "border-start" : ""} px-3 py-2"
                        role="button"
                    >
                        <Fa icon={investigationStatusMapping[investigationStatus]}/>
                        {Object.values(stats?.[investigationStatus] ?? {}).reduce((acc, val) => acc + val, 0)}
                    </div>
                {/each} 
            </div>
        </div>
        <div class="collapse mt-2" bind:this={extendedBlock}>
            <div class="d-inline-flex flex-column">
                <div class="d-flex bg-light-one p-2 rounded">
                    {#each Object.values(TestInvestigationStatus) as investigationStatus, idx}
                        <div class="{idx > 0 ? "ms-2" : ""} rounded bg-white">
                            <h6 class="p-2 border-bottom">
                                <Fa icon={investigationStatusMapping[investigationStatus]}/>
                                {TestInvestigationStatusStrings[investigationStatus]}
                                <span class="d-inline-block ms-3 text-end">{Object.values(stats?.[investigationStatus] ?? {}).reduce((acc, val) => acc + val, 0)}</span>
                            </h6>
                            <div class="p-2 d-flex flex-column">
                                {#each Object.values(TestStatus) as status}
                                    {#if stats[investigationStatus]?.[status]}
                                        <div class="flex-fill d-flex">
                                            <div class="me-4">{subUnderscores(titleCase(status))}</div>
                                            <div class="ms-auto fw-bold {StatusCSSClassMap[status]}">{stats[investigationStatus]?.[status]}</div>
                                        </div>
                                    {/if}
                                {/each}
                            </div>
                        </div>
                    {/each}
                </div>
                <button class="btn btn-dark mt-2" on:click={toggleExtendedInvestigations}>Hide</button>
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
