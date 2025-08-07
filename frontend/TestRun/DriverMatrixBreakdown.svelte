<script lang="ts">
    import { onMount } from "svelte";
    import type { TestCase, TestSuite } from "../Common/DriverMatrixTypes";
    import { faAnglesDown, faAnglesUp, faCheck, faCopy, faTimes } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import { titleCase } from "../Common/TextUtils";
    interface Props {
        suites?: TestSuite[];
        internalFilter?: string;
    }

    let { suites = [], internalFilter = $bindable("") }: Props = $props();

    interface ICaseSortPriorty {
        [key: string]: number
    }

    interface IStatusDisplayInfo {
        [key: string]: {
            show: boolean,
            testCount: number,
            class: string,
        }
    }

    interface ICaseExpansionInfo {
        [key: string]: boolean,
    }

    const caseSortPriority: ICaseSortPriorty = {
        failure: 0,
        error: 1,
        disabled: 7,
        passed: 10,
        skipped: 15,
    };

    const statusInfo: IStatusDisplayInfo = $state({
        failure: {
            show: true,
            testCount: 0,
            class: "bg-danger",
        },
        error: {
            show: true,
            testCount: 0,
            class: "bg-warning",
        },
        passed: {
            show: false,
            testCount: 0,
            class: "bg-success",
        },
        skipped: {
            show: false,
            testCount: 0,
            class: "bg-secondary",
        },
        disabled: {
            show: false,
            testCount: 0,
            class: "bg-dark",
        },
    });

    const expandedCases: ICaseExpansionInfo = $state({});

    const toggleStatus = function(status: string) {
        if (!statusInfo[status]) status = "disabled";
        statusInfo[status].show = !statusInfo[status].show;
    };

    const caseExpanded = function(testCase: TestCase, caseExpansionInfo: ICaseExpansionInfo) {
        return !!(caseExpansionInfo[`${testCase.name}+${testCase.classname}`]);
    };

    const handleExpandButtonClick = function (caseName: string, className: string, force = false) {
        const key = `${caseName}+${className}`;
        if (!force) {
            expandedCases[key] = !expandedCases[key];
        } else {
            expandedCases[key] = true;
        }
    };

    const handleCopyButtonClick = function(testCase: TestCase) {
        navigator.clipboard.writeText(`Test: ${testCase.name}\nClass: ${testCase.classname}\n \`\`\`${testCase.message ?? "No message."}\`\`\`\n`);
    };

    const shouldFilter = function (testCase: TestCase, filterString: string) {
        if (!filterString) return false;
        try {
            return !(new RegExp(filterString.toLowerCase()).test((testCase.name.toLowerCase() ?? "")));
        } catch {
            return false;
        }
    };

    const displayStatus = function (testCase: TestCase, filteredStatuses: IStatusDisplayInfo) {
        let status = testCase.status;
        if (!statusInfo[status]) status = "disabled";
        return filteredStatuses[status].show;
    };

    const aggregateSuites = function(suites: TestSuite[], statusInfo: IStatusDisplayInfo, filterString: string): TestCase[] {
        return suites
            .reduce<TestCase[]>((acc, suite) => [...acc, ...suite.cases], [])
            .sort((a: TestCase, b: TestCase) => {
                const lhs = caseSortPriority[a.status] ?? 99;
                const rhs = caseSortPriority[b.status] ?? 99;
                return lhs - rhs;
            })
            .filter((testCase) => displayStatus(testCase, statusInfo) && !shouldFilter(testCase, filterString));
    };


    const aggregateCaseCounts = function(suites: TestSuite[]) {
        suites.forEach((suite) => {
            suite.cases.forEach((testCase) => {
                let status = testCase.status;
                if (!statusInfo[status]) status = "disabled";
                statusInfo[status].testCount++;
                if (status == "failure" || status == "error") {
                    handleExpandButtonClick(testCase.name, testCase.classname, true);
                }
            });
        });
    };

    onMount(() => {
        aggregateCaseCounts(suites);
    });
</script>

<div class="d-flex my-2">
    {#each Object.entries(statusInfo) as [status, displayInfo]}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="ms-1 rounded px-2 py-1 {displayInfo.class} text-white cursor-pointer" onclick={() => toggleStatus(status)}>
            {#if displayInfo.show}
                <Fa icon={faCheck}/>
            {:else}
                <Fa icon={faTimes} />
            {/if}
            {titleCase(status)}
            ({displayInfo.testCount})
        </div>
    {/each}
</div>
<div class="mb-2">
    <input class="form-control" placeholder="Filter tests" type="text" bind:value={internalFilter}>
</div>
<div>
    {#each aggregateSuites(suites, statusInfo, internalFilter) as testCase}
        <div class="mb-2">
            <div class="mb-0 bg-light-three {caseExpanded(testCase, expandedCases) ? "rounded-top": "rounded"} p-2 border">
                <div class="d-flex">
                    <div>
                        {testCase.name}
                        <div class="text-small text-secondary">{testCase.classname}</div>
                    </div>
                    <div class="ms-auto rounded p-2 text-white {statusInfo[testCase.status]?.class ?? statusInfo.disabled.class}">
                        {testCase.status.toUpperCase()}
                    </div>
                    {#if testCase.message}
                    <button
                        class="ms-1 btn btn-primary"
                        title="More..."
                        onclick={() => handleExpandButtonClick(testCase.name, testCase.classname)}
                    >
                        {#if caseExpanded(testCase, expandedCases)}
                            <Fa icon={faAnglesUp} />
                        {:else}
                            <Fa icon={faAnglesDown} />
                        {/if}
                    </button>
                    {/if}
                    <button class="ms-1 btn btn-success me-2" title="Copy all" onclick={() => handleCopyButtonClick(testCase)}>
                        <Fa icon={faCopy} />
                    </button>
                </div>
            </div>
            {#if caseExpanded(testCase, expandedCases)}
            <div class="border-start border-end border-bottom bg-white p-2">
                {#if testCase.message}
                    <pre class="bg-light-one rounded m-0 p-2 case-message">{testCase.message}</pre>
                {:else}
                    <div class="text-center m-0 text-secondary">No message</div>
                {/if}
            </div>
            {/if}
        </div>
    {:else}
        <div class="my-2 text-center text-secondary">No cases to show.</div>
    {/each}
</div>

<style>
    .text-small {
        font-size: 0.8em;
    }

    .case-message {
        white-space: pre-wrap
    }

    .cursor-pointer {
        cursor: pointer;
    }
</style>
