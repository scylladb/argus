<script>
    import Test from "./Test.svelte";
    import { groupRequests, stats } from "./StatsSubscriber";
    import { StatusSortPriority } from "./TestStatus.js";
    import { sendMessage } from "./AlertStore";
    import NumberStats from "./NumberStats.svelte";
    export let release = "";
    export let group = {
        name: "",
        pretty_name: "",
        id: "",
    };
    export let filtered = false;
    const groupStatsTemplate = {
        created: 0,
        running: 0,
        passed: 0,
        failed: 0,
        total: -1,
        lastStatus: "unknown",
    };
    let groupStats = groupStatsTemplate;
    let tests = [];
    let testStatus = {};
    let clickedGroups = {};
    let testsReady = false;
    groupRequests.update((val) => [...val, [release, group.name]]);

    const sortTestsByStatus = function () {
        if (tests.length == 0) return;
        tests = tests.sort((a, b) => {
            let leftStatus =
                StatusSortPriority[testStatus[a.name]?.status] ??
                StatusSortPriority["none"];
            let rightStatus =
                StatusSortPriority[testStatus[b.name]?.status] ??
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

    stats.subscribe((val) => {
        groupStats =
            val["releases"]?.[release]?.["groups"]?.[group.name] ??
            groupStatsTemplate;
        testStatus = val["releases"]?.[release]?.["tests"];
        sortTestsByStatus();
    });

    const normalize = function (val, minVal, maxVal, total) {
        return ((val - minVal) / (maxVal - minVal)) * total;
    };

    const removeDots = function (str) {
        return str.replaceAll(".", "_");
    };

    const fetchTestNamesForReleaseGroup = async function (e) {
        if (clickedGroups[group.name]) return;
        tests = [];
        try {
            let apiResponse = await fetch("/api/v1/tests", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    release: release,
                    group: group,
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                tests = apiJson.response["tests"];
                clickedGroups[group.name] = true;
                sortTestsByStatus();
                testsReady = true;
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching release groups.\nMessage: ${error.message}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during release groups fetch"
                );
            }
        }
    };
</script>

<div class="accordion-item" class:d-none={filtered}>
    <h2 class="accordion-header" id="heading{removeDots(release)}{group.name}">
        <button
            class="accordion-button collapsed"
            data-bs-toggle="collapse"
            data-bs-target="#collapse{removeDots(release)}{group.name}"
            on:click={fetchTestNamesForReleaseGroup}
        >
            <div class="container-fluid p-0 m-0">
                <div class="row p-0 m-0">
                    <div class="col-8">
                        {group.pretty_name ?? group.name}
                    </div>
                    <div class="col-4 text-end">
                        {#if groupStats?.total > 0}
                            <NumberStats stats={groupStats} />
                        {:else if groupStats?.total == -1}
                            <span class="spinner-border spinner-border-sm" />
                        {:else}
                            <!-- svelte-ignore empty-block -->
                        {/if}
                    </div>
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
                            on:testRunRequest
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
