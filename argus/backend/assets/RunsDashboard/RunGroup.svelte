<script>
    import Test from "./Test.svelte";
    import { groupRequests, stats } from "./StatsSubscriber";
    import { StatusSortPriority } from "./TestStatus.js";
    import NumberStats from "./NumberStats.svelte";
    export let release = "";
    export let group = {
        name: "",
        pretty_name: "",
        id: "",
    };

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
                StatusSortPriority[testStatus[a.name]] ??
                StatusSortPriority["none"];
            let rightStatus =
                StatusSortPriority[testStatus[b.name]] ??
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

    const fetchTestNamesForReleaseGroup = function (e) {
        if (clickedGroups[group.name]) return;
        tests = [];
        fetch("/api/v1/tests", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                release: release,
                group: group,
            }),
        })
            .then((res) => {
                if (res.status == 200) {
                    return res.json();
                } else {
                    console.log("Something went wrong during test fetch");
                    console.log(res);
                }
            })
            .then((res) => {
                if (res.status === "ok") {
                    console.log(res);
                    tests = res.response["tests"];
                    clickedGroups[group.name] = true;
                    sortTestsByStatus();
                    testsReady = true;
                } else {
                    console.log("API Error after fetch");
                    console.log(res.response);
                }
            });
    };
</script>

<div class="accordion-item">
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
        class="accordion-collapse collapse accordion-tests"
        id="collapse{removeDots(release)}{group.name}"
    >
        {#if testsReady}
            <ul
                class="list-group list-group-flush list-group-tests border-start"
            >
                {#each tests as test (test.id)}
                    <Test
                        {release}
                        {test}
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
    .accordion-tests {
        margin-left: 2rem;
    }
</style>
