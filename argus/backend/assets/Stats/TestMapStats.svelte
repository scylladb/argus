<script>
    import { createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import {
        faSearch,
        faEyeSlash,
        faEye,
        faBug,
        faAngleRight,
    } from "@fortawesome/free-solid-svg-icons";

    import {
        StatusBackgroundCSSClassMap,
        TestInvestigationStatus,
        TestInvestigationStatusStrings,
        TestStatus,
    } from "../Common/TestStatus";
    export let clickedTests = {};
    export let stats = {
        tests: {
            example: {
                status: "failed",
                start_time: 12654364536,
            },
        },
    };

    const investigationStatusIcon = {
        in_progress: faEye,
        not_investigated: faEyeSlash,
        investigated: faSearch,
    };

    const dispatch = createEventDispatcher();

    const handleTestClick = function (name, test) {
        if (test.start_time == 0) return;
        dispatch("testClick", {
            name: name,
            status: test.status,
            start_time: test.start_time,
            last_runs: test.last_runs,
        });
    };

    const filterTestsForGroup = function (groupName, tests) {
        return Object.values(tests)
            .filter((test) => test.group == groupName)
            .reduce((tests, test) => {
                tests[test.name] = test;
                return tests;
            }, {});
    };
</script>

{#each Object.entries(stats.groups) as [groupName, group] (groupName)}
    <div>
        <h5>{groupName}</h5>
        <div class="my-2 d-flex flex-wrap">
            {#each Object.entries(filterTestsForGroup(groupName, stats.tests)) as [testName, test] (testName)}
                <div
                    on:click={() => {
                        handleTestClick(testName, test);
                    }}
                    class:status-block-active={test.start_time != 0}
                    class="d-inline-block border status-block {StatusBackgroundCSSClassMap[
                        test.status
                    ]}"
                >
                    <div
                        class="position-absolute status-block-popup shadow p-1"
                    >
                        {testName}
                    </div>
                    <div
                        class="d-flex h-100 align-items-center justify-content-center p-2 status-block-inner"
                    >
                        {#if clickedTests[testName]}
                            <Fa
                                color="#fff"
                                icon={faAngleRight}
                            />
                        {/if}
                        {#if test.investigation_status && (test.status != TestStatus.PASSED || test.investigation_status != TestInvestigationStatus.NOT_INVESTIGATED)}
                            <div
                                class="p-1"
                                title="Investigation: {TestInvestigationStatusStrings[
                                    test.investigation_status
                                ]}"
                            >
                                <Fa
                                    color="#fff"
                                    icon={investigationStatusIcon[
                                        test.investigation_status
                                    ]}
                                />
                            </div>
                        {/if}
                        {#if test.hasBugReport}
                            <div class="p-1" title="Has a bug report">
                                <Fa color="#fff" icon={faBug} />
                            </div>
                        {/if}
                    </div>
                </div>
            {:else}
                <div class="text-muted my-2">No tests for this group</div>
            {/each}
        </div>
    </div>
{/each}

<style>
    .status-block {
        cursor: help;
        width: 64px;
        height: 64px;
        position: relative;
    }

    .status-block-active:hover {
        cursor: pointer;
    }

    .status-block-active:hover > .status-block-inner {
        border: 2px solid black;
    }

    .status-block-popup {
        display: none;
        width: 256px;
        font-size: 0.9em;
        background-color: white;
        border: solid 1px white;
        font-family: monospace;
        border-radius: 8px;
        top: -2.5em;
        z-index: 999;
    }

    .status-block:hover > .status-block-popup {
        display: block;
    }
</style>
