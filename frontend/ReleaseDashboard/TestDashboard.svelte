<script>
    import { createEventDispatcher, onDestroy, onMount } from "svelte";
    import Fa from "svelte-fa";
    import {
        faSearch,
        faEyeSlash,
        faEye,
        faBug,
        faComment,
        faArrowDown,
        faArrowUp,
    } from "@fortawesome/free-solid-svg-icons";

    import {
        StatusBackgroundCSSClassMap,
        TestInvestigationStatus,
        TestInvestigationStatusStrings,
        TestStatus,
    } from "../Common/TestStatus";
    import { subUnderscores, titleCase } from "../Common/TextUtils";
    import { apiMethodCall } from "../Common/ApiUtils";
    import AssigneeList from "../WorkArea/AssigneeList.svelte";
    import { userList } from "../Stores/UserlistSubscriber";
    import { getPicture } from "../Common/UserUtils";
    export let releaseName = "";
    export let releaseId = "";
    export let clickedTests = {};
    export let productVersion;
    let stats;
    let statRefreshInterval;
    let users = {};
    $: users = $userList;
    let assigneeList = {
        groups: {

        },
        tests: {

        }
    };

    const investigationStatusIcon = {
        in_progress: faSearch,
        not_investigated: faEyeSlash,
        investigated: faEye,
    };

    const dispatch = createEventDispatcher();

    const loadCollapseState = function() {
        return JSON.parse(window.localStorage.getItem(`releaseDashState-${releaseId}`)) || {};
    };

    const toggleCollapse = function(collapseId) {
        collapseState[collapseId] = !(collapseState[collapseId] || false);
        window.localStorage.setItem(`releaseDashState-${releaseId}`, JSON.stringify(collapseState));
    };

    const getCollapseState = function(collapseId) {
        return collapseState[collapseId] ?? false;
    };

    let collapseState = loadCollapseState();


    const fetchStats = async function () {
        let params = new URLSearchParams({
            release: releaseName,
            limited: new Number(false),
            force: new Number(true),
            productVersion: productVersion ?? "",
        });
        let response = await fetch("/api/v1/release/stats/v2?" + params);
        let json = await response.json();
        if (json.status != "ok") {
            return false;
        }
        stats = json.response;

        if (stats.release.perpetual) {
            fetchGroupAssignees(releaseId);
        } else {
            Object.values(stats.groups).forEach((groupStat, idx) => {
                setTimeout(() => {
                    fetchTestAssignees(groupStat.group.id);
                }, 25 * idx);
            });
        }
    };

    const fetchVersions = async function() {
        let response = await fetch(`/api/v1/release/${releaseId}/versions`);
        if (response.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await response.json();
        if (json.status !== "ok") {
            return Promise.reject(json.exception);
        }

        return json.response;
    };

    const handleVersionClick = function(versionString) {
        productVersion = versionString;
        fetchStats();
        dispatch("versionChange", { version: productVersion });
    };

    const handleTestClick = function (testStats, groupStats) {
        dispatch("testClick", {
            name: testStats.test.name,
            id: testStats.test.id,
            assignees: [...(assigneeList.tests?.[testStats.test.id] ?? []), ...(assigneeList.groups?.[groupStats.group.id] ?? [])],
            group: groupStats.group.name,
            status: testStats.status,
            start_time: testStats.start_time,
            last_runs: testStats.last_runs,
            build_system_id: testStats.test.build_system_id,
        });
    };

    const sortTestStats = function (testStats) {
        const testPriorities = {
            failed: 6,
            passed: 5,
            running: 4,
            created: 3,
            aborted: 2,
            not_run: 1,
            not_planned: 0,
            unknown: -1,

        };
        let tests = Object.values(testStats)
            .sort((a, b) => testPriorities[b.status] - testPriorities[a.status])
            .reduce((tests, testStats) => {
                tests[testStats.test.id] = testStats;
                return tests;
            }, {});
        return tests;
    };

    const fetchGroupAssignees = async function(releaseId) {
        let params = new URLSearchParams({
            releaseId: releaseId,
        });
        let result = await apiMethodCall("/api/v1/release/assignees/groups?" + params, undefined, "GET");
        if (result.status === "ok") {
            assigneeList.groups = Object.assign(assigneeList.groups, result.response);
        }
    };

    const fetchTestAssignees = async function(groupId) {
        let params = new URLSearchParams({
            groupId: groupId,
        });
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

    const sortedGroups = function (groups) {
        return Object
            .values(groups)
            .sort((lhs, rhs) => {
                let lhsKey = lhs.group.pretty_name || lhs.group.name;
                let rhsKey = rhs.group.pretty_name || rhs.group.name;
                return lhsKey >= rhsKey ? 1 : -1;
            });
    };

    onMount(() => {
        fetchStats();
        let refreshInterval = 300 + 15 + Math.round((Math.random() * 10));
        statRefreshInterval = setInterval(() => {
            fetchStats();
        }, refreshInterval * 1000);
    });

    onDestroy(() => {
        if (statRefreshInterval) {
            clearInterval(statRefreshInterval);
        }
    });

</script>
<div class="rounded bg-light-one shadow-sm p-2">
    {#await fetchVersions()}
        <div>Loading versions...</div>
    {:then versions}
        <div class="d-flex flex-wrap p-2">
            <button
                class="btn ms-2 mb-2"
                class:btn-primary={!productVersion}
                class:btn-light={productVersion}
                on:click={() => { handleVersionClick(""); }}>All</button>
            {#each versions as version}
                <button
                    class="btn btn-light ms-2 mb-2"
                    class:btn-primary={productVersion == version}
                    class:btn-light={productVersion != version}
                    on:click={() => { handleVersionClick(version); }}>{version}</button>
            {/each}
        </div>
    {/await}
    {#if stats}
        {#each sortedGroups(stats.groups) as groupStats (groupStats.group.id)}
            {#if !groupStats.disabled}
                <div class="p-2 shadow mb-2 rounded bg-main">
                    <h5 class="mb-2 d-flex">
                        <div>
                            <div class="mb-2">{groupStats.group.pretty_name || groupStats.group.name}</div>
                            {#if Object.keys(assigneeList.groups).length > 0 && Object.keys(users).length > 0}
                                <div class="shadow-sm bg-main rounded d-inline-block p-2">
                                    <div class="d-flex align-items-center">
                                        <img
                                            class="img-thumb ms-2"
                                            src={getPicture(
                                                users[assigneeList.groups[groupStats.group.id]?.[0]]
                                                    ?.picture_id
                                            )}
                                            alt=""
                                        />
                                        <span class="ms-2 fs-6"
                                            >{users[assigneeList.groups[groupStats.group.id]?.[0]]
                                                ?.full_name ?? "unassigned"}</span
                                        >
                                    </div>
                                </div>
                            {/if}
                        </div>
                        <div class="ms-auto">
                            <button
                                class="btn btn-sm"
                                data-bs-toggle="collapse"
                                data-bs-target="#collapse-{groupStats.group.id}"
                                on:click={() => {
                                    toggleCollapse(`collapse-${groupStats.group.id}`);
                                }}
                            >
                            {#if getCollapseState(`collapse-${groupStats.group.id}`, collapseState)}
                                <Fa icon={faArrowDown}/>
                            {:else}
                                <Fa icon={faArrowUp}/>
                            {/if}
                            </button>
                        </div>
                    </h5>
                    <div class="collapse" class:show={!getCollapseState(`collapse-${groupStats.group.id}`)} id="collapse-{groupStats.group.id}">
                        <div class="my-2 d-flex flex-wrap bg-lighter rounded shadow-sm">
                            {#each Object.entries(sortTestStats(groupStats.tests)) as [testId, testStats] (testId)}
                                <div
                                    class:status-block-active={testStats.start_time != 0}
                                    class:investigating={testStats?.investigation_status == TestInvestigationStatus.IN_PROGRESS}
                                    class:should-be-investigated={testStats?.investigation_status == TestInvestigationStatus.NOT_INVESTIGATED && testStats?.status == TestStatus.FAILED}
                                    class="rounded bg-main status-block m-1 d-flex flex-column overflow-hidden shadow-sm"
                                    on:click={() => {
                                        handleTestClick(testStats, groupStats);
                                    }}
                                >
                                    <div
                                        class="{StatusBackgroundCSSClassMap[
                                            testStats.status
                                        ]} text-center text-light p-1 border-bottom"
                                    >
                                        {testStats.status == "unknown"
                                            ? "Not run"
                                            : subUnderscores(titleCase(testStats.status))}
                                        {#if clickedTests[testStats.test.id]}
                                            <div class="text-tiny">Selected</div>
                                        {/if}
                                    </div>
                                    <div class="p-1 text-small d-flex align-items-center">
                                        <div class="ms-1">{testStats.test.name}</div>
                                    </div>
                                    <div class="d-flex flex-fill align-items-end justify-content-end p-1">
                                        <div class="p-1 me-auto">
                                            {#if assigneeList.tests[testStats.test.id] || assigneeList.groups[groupStats.group.id] || testStats.last_runs?.[0]?.assignee}
                                                <AssigneeList
                                                    smallImage={false}
                                                    assignees={getAssigneesForTest(
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
                                                    testStats.investigation_status
                                                ]}"
                                            >
                                                <Fa
                                                    color="#000"
                                                    icon={investigationStatusIcon[
                                                        testStats.investigation_status
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
                                </div>
                            {:else}
                                <div class="text-dark m-2">No tests for this group</div>
                            {/each}
                        </div>
                    </div>
                </div>
            {/if}
        {/each}

    {:else}
        <div class="d-flex align-items-center justify-content-center text-center">
            <div class="spinner-grow"></div>
            <div class="ms-2 text-bold">Loading Test Dashboard...</div>
        </div>
    {/if}
</div>

<style>
    .status-block {
        width: 178px;
        max-height: 160px;
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
