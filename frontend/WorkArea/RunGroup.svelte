<script lang="ts">
    import { StatusSortPriority } from "../Common/TestStatus";
    import { apiMethodCall } from "../Common/ApiUtils";
    import NumberStats from "../Stats/NumberStats.svelte";
    import AssigneeList from "./AssigneeList.svelte";
    import Test from "./Test.svelte";
    import { sanitizeSelector } from "../Common/TextUtils";
    interface Props {
        release?: string;
        group?: any;
        filtered?: boolean;
        assigneeList?: any;
        runs?: any;
        groupStats: any;
        releaseObject: any;
    }

    let {
        release = "",
        group = {
        name: "",
        pretty_name: "",
        id: "",
    },
        filtered = false,
        assigneeList = [],
        runs = $bindable([]),
        groupStats,
        releaseObject
    }: Props = $props();

    let groupClicked = $state(false);
    let testAssignees = $state({});
    let tests = $state([]);

    const sortTestsByStatus = function (tests) {
        if (tests.length == 0 || !groupStats) return tests;
        return tests.sort((a, b) => {
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

    const fetchTests = async function () {
        let params = new URLSearchParams({
            groupId: group.id
        });
        let res = await fetch("/api/v1/tests?" + params);
        if (res.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await res.json();
        if (json.status != "ok") {
            return Promise.reject(json.exception);
        }
        tests = sortTestsByStatus(json.response);
        fetchTestAssignees();
    };

    const fetchTestAssignees = async function () {
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
        }
    };

    let filterString = $state("");
    const isFiltered = function (name = "") {
        if (filterString == "") {
            return false;
        }
        return !RegExp(filterString.toLowerCase()).test(name.toLowerCase());
    };

    const handleGroupClick = async function (e) {
        groupClicked = !groupClicked;
    };

</script>

<div class="accordion-item" class:d-none={filtered}>
    <h2 class="accordion-header" id="heading{sanitizeSelector(`${release}_${group.name}`)}">
        <button
            class="accordion-button collapsed"
            data-bs-toggle="collapse"
            data-bs-target="#collapse-{group.id}"
            onclick={handleGroupClick}
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
                            <!-- svelte-ignore block_empty -->
                        {:else if groupStats?.total == 0}
                            <!-- svelte-ignore block_empty -->
                        {:else if !releaseObject.enabled || releaseObject.dormant}
                            <!-- svelte-ignore block_empty -->
                        {:else}
                            <span class="spinner-border spinner-border-sm"></span>
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
        id="collapse-{group.id}"
    >
    {#if groupClicked}
        {#await fetchTests()}
            <div class="row">
                <div class="col text-center p-1">
                    <span class="spinner-border spinner-border-sm"></span> Loading...
                </div>
            </div>
        {:then}
            <div class="p-2 border-bottom">
                <input
                    class="form-control"
                    type="text"
                    placeholder="Filter tests"
                    bind:value={filterString}
                    oninput={() => {
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
                            {test}
                            filtered={isFiltered(test.name)}
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
        {/await}
    {/if}
    </div>
</div>

<style>
    .list-tests {
        margin-left: 2rem;
        background-color: #fff;
    }
</style>
