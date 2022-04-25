<script>
    import { stats } from "../Stores/StatsSubscriber";
    import { allTests } from "../Stores/WorkspaceStore";
    import { StatusSortPriority } from "../Common/TestStatus";
    import { apiMethodCall } from "../Common/ApiUtils";
    import NumberStats from "../Stats/NumberStats.svelte";
    import AssigneeList from "./AssigneeList.svelte";
    import Test from "./Test.svelte";
    import { onMount } from "svelte";
    export let release = "";
    export let group = {
        name: "",
        pretty_name: "",
        id: "",
    };
    export let filtered = false;
    export let assigneeList = [];
    export let runs = {};

    const groupStatsTemplate = {
        created: 0,
        running: 0,
        passed: 0,
        failed: 0,
        total: -1,
        lastStatus: "unknown",
        tests: {},
        dormant: true,
    };
    let groupStats = groupStatsTemplate;
    let groupClicked = false;
    let testAssignees = {};
    let tests = [];
    let testStatus = {};
    let clickedGroups = {};
    let testsReady = false;

    const sortTestsByStatus = function () {
        if (tests.length == 0) return;
        tests = tests.sort((a, b) => {
            let leftStatus =
                StatusSortPriority?.[testStatus?.[a.name]?.status] ??
                StatusSortPriority["none"];
            let rightStatus =
                StatusSortPriority?.[testStatus?.[b.name]?.status] ??
                StatusSortPriority["none"];
            if (leftStatus > rightStatus) {
                return 1;
            } else if (leftStatus < rightStatus) {
                return -1;
            } else {
                return 0;
            }
        });
    };

    let filterString = "";
    const isFiltered = function (name = "") {
        if (filterString == "") {
            return false;
        }
        return !RegExp(filterString.toLowerCase()).test(name.toLowerCase());
    };

    allTests.subscribe((val) => {
        if (!val) return;
        tests = val.filter((test) => test.group_id == group.id);
        clickedGroups[group.name] = true;
        sortTestsByStatus();
        testsReady = true;
    });

    const handleGroupClick = async function (e) {
        if (groupClicked) return;
        let params = new URLSearchParams({
            groupId: group.id,
        });
        let result = await apiMethodCall(
            "/api/v1/release/assignees/tests?" + params,
            undefined,
            "GET"
        );
        if (result.status === "ok") {
            testAssignees = result.response;
            groupClicked = true;
        }
    };

    const normalize = function (val, minVal, maxVal, total) {
        return ((val - minVal) / (maxVal - minVal)) * total;
    };

    const removeDots = function (str) {
        return str.replaceAll(".", "_");
    };

    onMount(() => {
        stats.subscribe((val) => {
            groupStats =
                val["releases"]?.[release]?.["groups"]?.[group.name] ??
                groupStatsTemplate;
            testStatus = groupStats["tests"];
            sortTestsByStatus();
        });
    });
</script>

<div class="accordion-item" class:d-none={filtered}>
    <h2 class="accordion-header" id="heading{removeDots(release)}{group.name}">
        <button
            class="accordion-button collapsed"
            data-bs-toggle="collapse"
            data-bs-target="#collapse{removeDots(release)}{group.name}"
            on:click={handleGroupClick}
        >
            <div class="container-fluid p-0 m-0">
                <div class="row p-0 m-0">
                    <div class="col-8">
                        {group.pretty_name || group.name}
                    </div>
                    <div class="col-4 text-end">
                        {#if groupStats?.total > 0}
                            <NumberStats stats={groupStats} />
                        {:else if groupStats?.total ?? 0 == 0}
                            <!-- svelte-ignore empty-block -->
                        {:else if groupStats?.dormant ?? false}
                            <!-- svelte-ignore empty-block -->
                        {:else}
                            <span class="spinner-border spinner-border-sm" />
                        {/if}
                    </div>
                </div>
                <div class="row p-0 m-0">
                    <AssigneeList assignees={assigneeList} />
                </div>
            </div>
        </button>
    </h2>
    <div
        class="accordion-collapse collapse"
        id="collapse{removeDots(release)}{group.name}"
    >
        {#if testsReady}
            <div class="p-2 border-bottom">
                <input
                    class="form-control"
                    type="text"
                    placeholder="Filter tests"
                    bind:value={filterString}
                    on:input={() => {
                        tests = tests;
                    }}
                />
            </div>
            <div class="bg-light">
                <ul
                    class="list-tests list-group list-group-flush list-group-tests border-start"
                >
                    {#each tests as test (test.id)}
                        <Test
                            {release}
                            {test}
                            filtered={isFiltered(test.name)}
                            group={group.name}
                            assigneeList={testAssignees?.[test.id] ?? []}
                            bind:runs
                            on:testRunRequest
                            on:testRunRemove
                        />
                    {:else}
                        <div class="row">
                            <div class="col text-center text-muted p-1">
                                No tests available.
                            </div>
                        </div>
                    {/each}
                </ul>
            </div>
        {:else}
            <div class="row">
                <div class="col text-center p-1">
                    <span class="spinner-border spinner-border-sm" /> Loading...
                </div>
            </div>
        {/if}
    </div>
</div>

<style>
    .list-tests {
        margin-left: 2rem;
        background-color: #fff;
    }
</style>
