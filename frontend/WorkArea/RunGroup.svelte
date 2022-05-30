<script>
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
    export let groupStats;

    let groupClicked = false;
    let testAssignees = {};
    let tests = [];
    let clickedGroups = {};
    let testsReady = false;

    const sortTestsByStatus = function () {
        if (tests.length == 0 || !groupStats) return;
        tests = tests.sort((a, b) => {
            let leftStatus =
                StatusSortPriority?.[groupStats?.tests?.[a.id]?.status] ??
                StatusSortPriority["none"];
            let rightStatus =
                StatusSortPriority?.[groupStats?.tests?.[b.id]?.status] ??
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

    const removeDots = function (str) {
        return str.replaceAll(".", "_");
    };

    onMount(() => {
        sortTestsByStatus();
    });
</script>

<div class="accordion-item" class:d-none={filtered}>
    <h2 class="accordion-header" id="heading{removeDots(`${release}_${group.name}`)}">
        <button
            class="accordion-button collapsed"
            data-bs-toggle="collapse"
            data-bs-target="#collapse{removeDots(`${release}_${group.name}`)}"
            on:click={handleGroupClick}
        >
            <div class="d-flex flex-column w-100">
                <div class="mb-1">
                    {group.pretty_name || group.name}
                </div>
                <div class="d-flex">
                    <div class="w-25">
                        {#if groupStats?.total > 0}
                            <NumberStats stats={groupStats} />
                        {:else if groupStats?.disabled ?? false}
                            <!-- svelte-ignore empty-block -->
                        {:else if groupStats?.total == 0}
                            <!-- svelte-ignore empty-block -->
                        {:else}
                            <span class="spinner-border spinner-border-sm" />
                        {/if}
                    </div>
                    <div class="ms-auto me-4">
                        <AssigneeList assignees={assigneeList} />
                    </div>
                </div>
            </div>
        </button>
    </h2>
    <div
        class="accordion-collapse collapse"
        id="collapse{removeDots(`${release}_${group.name}`)}"
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
                            testStats={groupStats?.tests?.[test.id]}
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
