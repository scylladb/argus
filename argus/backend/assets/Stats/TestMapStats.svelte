<script>
    import { createEventDispatcher, onMount } from "svelte";
    import Fa from "svelte-fa";
    import {
        faSearch,
        faEyeSlash,
        faEye,
        faBug,
        faComment,
    } from "@fortawesome/free-solid-svg-icons";

    import {
        StatusBackgroundCSSClassMap,
        StatusCSSClassMap,
        TestInvestigationStatus,
        TestInvestigationStatusStrings,
        TestStatus,
    } from "../Common/TestStatus";
    import { titleCase } from "../Common/TextUtils";
    import { apiMethodCall } from "../Common/ApiUtils";
    import AssigneeList from "../WorkArea/AssigneeList.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    import { getPicture } from "../Common/UserUtils";
    export let releaseName = "";
    export let releaseId = "";
    export let clickedTests = {};
    export let stats = {
        tests: {
            example: {
                status: "failed",
                start_time: 12654364536,
            },
        },
    };
    let users = {};
    $: users = $userList;
    let assigneeList = {
        groups: {

        },
        tests: {
            
        }
    };

    const investigationStatusIcon = {
        in_progress: faEye,
        not_investigated: faEyeSlash,
        investigated: faSearch,
    };

    const dispatch = createEventDispatcher();

    const handleTestClick = function (name, test, groupName, group) {
        dispatch("testClick", {
            name: name,
            assignees: [...(assigneeList.tests?.[test.test_id] ?? []), ...(assigneeList.groups?.[group.group_id] ?? [])],
            group: groupName,
            status: test.status,
            start_time: test.start_time,
            last_runs: test.last_runs,
            build_system_id: test.build_system_id,
        });
    };

    const filterTestsForGroup = function (groupName, tests) {
        let testPriorities = {
            failed: 5,
            passed: 4,
            running: 3,
            created: 2,
            aborted: 1,
            unknown: 0,
        };
        return Object.values(tests)
            .filter((test) => test.group == groupName)
            .sort((a, b) => testPriorities[b.status] - testPriorities[a.status])
            .reduce((tests, test) => {
                tests[test.name] = test;
                return tests;
            }, {});
    };

    const fetchGroupAssignees = async function(releaseId) {
        let params = new URLSearchParams({
            releaseId: releaseId,
        })
        let result = await apiMethodCall("/api/v1/release/assignees/groups?" + params, undefined, "GET");
        if (result.status === "ok") {
            assigneeList.groups = Object.assign(assigneeList.groups, result.response);
        }
    };

    const fetchTestAssignees = async function(groupId) {
        let params = new URLSearchParams({
            groupId: groupId,
        })
        let result = await apiMethodCall("/api/v1/release/assignees/tests?" + params, undefined, "GET");
        if (result.status === "ok") {
            assigneeList.tests = Object.assign(assigneeList.tests, result.response);
        }
    };

    const getAssigneesForTest = function (testId, groupId, last_runs) {
        let testAssignees = assigneeList.tests?.[testId] ?? [];
        let groupAssignees = assigneeList.groups?.[groupId] ?? [];
        let allAssignees = [...testAssignees, ...groupAssignees];
        let lastRun = last_runs?.[0];
        if (lastRun?.assignee && allAssignees.findIndex(v => v == lastRun.assignee) == -1)
        {
            return [lastRun.assignee];
        }
        return allAssignees;
    };

    onMount(() => {
        if (stats.perpetual) {
            fetchGroupAssignees(releaseId);
        } else {
            Object.values(stats.groups).forEach((group, idx) => {
                setTimeout(() => {
                    fetchTestAssignees(group.group_id);
                }, 25 * idx);
            })
        }
    });
</script>

{#each Object.entries(stats.groups) as [groupName, group] (groupName)}
    <div class="p-2 shadow mb-2 rounded bg-main">
        <h5 class="mb-2">
            <div class="mb-2">{groupName}</div>
            {#if Object.keys(assigneeList.groups).length > 0 && Object.keys(users).length > 0}
                <div class="shadow-sm bg-main rounded d-inline-block p-2">
                    <div class="d-flex align-items-center">
                        <img
                            class="img-thumb ms-2"
                            src={getPicture(
                                users[assigneeList.groups[group.group_id]?.[0]]
                                    ?.picture_id
                            )}
                            alt=""
                        />
                        <span class="ms-2 fs-6"
                            >{users[assigneeList.groups[group.group_id]?.[0]]
                                ?.full_name ?? "unassigned"}</span
                        >
                    </div>
                </div>
            {/if}
        </h5>
        <div class="my-2 d-flex flex-wrap bg-lighter rounded shadow-sm">
            {#each Object.entries(filterTestsForGroup(groupName, group.tests ?? {})) as [testName, test] (`${groupName}/${testName}`)}
                <div
                    class:status-block-active={test.start_time != 0}
                    class="rounded bg-main status-block m-1 d-flex flex-column overflow-hidden shadow-sm"
                    on:click={() => {
                        handleTestClick(testName, test, groupName, group);
                    }}
                >
                    <div
                        class="{StatusBackgroundCSSClassMap[
                            test.status
                        ]} text-center text-light p-1 border-bottom"
                    >
                        {test.status == "unknown"
                            ? "Not run"
                            : titleCase(test.status)}
                        {#if clickedTests[`${groupName}/${testName}`]}
                            <div class="text-tiny">Selected</div>
                        {/if}
                    </div>
                    <div class="p-1 text-small d-flex align-items-center">
                        <div class="ms-1">{testName}</div>
                    </div>
                    <div class="d-flex flex-fill align-items-end justify-content-end p-1">
                        <div class="p-1 me-auto">
                            {#if assigneeList.tests[test.test_id] || assigneeList.groups[group.group_id]}
                                <AssigneeList
                                    smallImage={false}
                                    assignees={getAssigneesForTest(
                                        test.test_id,
                                        group.group_id,
                                        test.last_runs ?? [],
                                    )}
                                />
                            {/if}
                        </div>
                        {#if test.investigation_status && (test.status != TestStatus.PASSED || test.investigation_status != TestInvestigationStatus.NOT_INVESTIGATED)}
                            <div
                                class="p-1"
                                title="Investigation: {TestInvestigationStatusStrings[
                                    test.investigation_status
                                ]}"
                            >
                                <Fa
                                    color="#000"
                                    icon={investigationStatusIcon[
                                        test.investigation_status
                                    ]}
                                />
                            </div>
                        {/if}
                        {#if test.hasBugReport}
                            <div class="p-1" title="Has a bug report">
                                <Fa color="#000" icon={faBug} />
                            </div>
                        {/if}
                        {#if test.hasComments}
                            <div class="p-1" title="Has a comment">
                                <Fa color="#000" icon={faComment} />
                            </div>
                        {/if}
                    </div>
                </div>
            {:else}
                <div class="text-dark m-2">No tests for this group</div>
            {/each}
        </div>
    </div>
{/each}

<style>
    .status-block {
        width: 178px;
        max-height: 160px;
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
</style>
