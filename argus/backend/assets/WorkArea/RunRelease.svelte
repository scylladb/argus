<script>
    import { sendMessage } from "../Stores/AlertStore";
    import { releaseRequests, stats } from "../Stores/StatsSubscriber";
    import { assigneeStore, requestAssigneesForReleaseGroups } from "../Stores/AssigneeSubscriber";
    import NumberStats from "../Stats/NumberStats.svelte";
    import RunGroup from "./RunGroup.svelte";
    let releaseGroups = [];
    export let release = {
        name: "undefined",
        pretty_name: "undefined",
    };
    export let filtered = false;
    export let runs = {};
    let fetched = false;
    const releaseStatsDefault = {
        created: 0,
        running: 0,
        passed: 0,
        failed: 0,
        aborted: 0,
        lastStatus: "unknown",
        disabled: true,
        groups: {},
        tests: {},
        total: -1,
    };
    let releaseStats = releaseStatsDefault;
    let groupStats = {};
    let filterString = "";
    let assigneeList = [];
    $: assigneeList = $assigneeStore?.[release.name] ?? {
        groups: [],
        tests: []
    };
    const sortGroupsByStatus = function () {
        if (releaseGroups.length == 0) return;
        releaseGroups = releaseGroups.sort((a, b) => {
            let leftOrder = groupStats[a.name]?.total ?? 0;
            let rightOrder = groupStats[b.name]?.total ?? 0;
            if (leftOrder > rightOrder) {
                return -1;
            } else if (rightOrder > leftOrder) {
                return 1;
            } else {
                return 0;
            }
        });
    };

    const isFiltered = function (name = "") {
        if (filterString == "") {
            return false;
        }
        return !RegExp(filterString.toLowerCase()).test(name.toLowerCase());
    };

    releaseRequests.update((val) => [...val, release.name]);
    stats.subscribe((val) => {
        releaseStats = val["releases"]?.[release.name] ?? releaseStatsDefault;
        groupStats =
            val["releases"]?.[release.name]?.["groups"] ?? releaseStatsDefault;
        sortGroupsByStatus();
    });

    const removeDots = function (str) {
        return str.replaceAll(".", "_");
    };

    const fetchGroupsForRelease = async function (e) {
        if (fetched) return;
        try {
            let apiResponse = await fetch("/api/v1/release_groups", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    release: release,
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                releaseGroups = apiJson.response;
                sortGroupsByStatus();
                requestAssigneesForReleaseGroups(release.name, releaseGroups.map(val => val.name));
                fetched = true;
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching release groups.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during release groups fetch"
                );
                console.log(error);
            }
        }
    };
</script>

<div class="accordion-item" class:d-none={filtered}>
    <h2 class="accordion-header" id="heading{removeDots(release.name)}">
        <button
            class="accordion-button collapsed"
            data-argus-release={release.name}
            data-bs-toggle="collapse"
            data-bs-target="#collapse{removeDots(release.name)}"
            on:click={fetchGroupsForRelease}
            ><div class="container-fluid p-0 m-0">
                <div class="row p-0 m-0">
                    <div class="col-8">
                        {release.pretty_name || release.name}
                    </div>
                    <div class="col-4 text-end">
                        {#if releaseStats?.total > 0}
                            <NumberStats stats={releaseStats} />
                        {:else if releaseStats?.total == -1}
                            <span class="spinner-border spinner-border-sm" />
                        {:else}
                            <!-- svelte-ignore empty-block -->
                        {/if}
                    </div>
                </div>
            </div></button
        >
    </h2>
    <div
        class="accordion-collapse collapse"
        id="collapse{removeDots(release.name)}"
    >
        <div class="p-2">
            <a
                href="/dashboard/{release.name}"
                class="btn btn-sm btn-dark"
                target="_blank">Dashboard</a
            >
        </div>
        <div class="p-2 border-bottom">
            <input
                class="form-control"
                type="text"
                placeholder="Filter groups"
                bind:value={filterString}
                on:input={() => {
                    releaseGroups = releaseGroups;
                }}
            />
        </div>
        <div class="bg-light">
            <div
                class="accordion accordion-flush accordion-release-groups border-start bg-white"
                id="accordionGroups{removeDots(release.name)}"
            >
                {#each releaseGroups ?? [] as group (group.id)}
                    <RunGroup
                        release={release.name}
                        {group}
                        filtered={isFiltered(group.pretty_name ?? group.name)}
                        parent="#accordionGroups{release.name}"
                        assigneeList={assigneeList?.groups[group.name] ?? []}
                        bind:runs={runs}
                        on:testRunRequest
                        on:testRunRemove
                    />
                {:else}
                    <div class="row">
                        <div class="col text-center p-1">
                            <span class="spinner-border spinner-border-sm" /> Loading...
                        </div>
                    </div>
                {/each}
            </div>
        </div>
    </div>
</div>

<style>
    #dashboard-main {
        border-bottom: solid 1px gray;
    }
    #run-sidebar {
        border-right: 1px solid gray;
    }

    .accordion-release-groups {
        margin-left: 2rem;
    }

    .bg-white {
        background-color: #fff;
    }
</style>
