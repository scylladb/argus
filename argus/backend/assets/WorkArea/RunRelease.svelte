<script>
    import { onDestroy, onMount } from "svelte";
    import { allGroups } from "../Stores/WorkspaceStore";
    import {
        stats,
        requestReleaseStats,
        removeReleaseRequest,
    } from "../Stores/StatsSubscriber";
    import NumberStats from "../Stats/NumberStats.svelte";
    import { apiMethodCall } from "../Common/ApiUtils";
    import RunGroup from "./RunGroup.svelte";
    export let release = {
        name: "undefined",
        pretty_name: "undefined",
    };
    export let filtered = false;
    export let runs = {};

    let releaseClicked = false;
    let releaseGroups = [];
    const unsub = allGroups.subscribe((groups) => {
        if (!groups) return;
        releaseGroups = groups.filter(
            (group) => group.release_id == release.id
        );
    });

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
    let assigneeList = {};

    const isFiltered = function (name = "") {
        if (filterString == "") {
            return false;
        }
        return !RegExp(filterString.toLowerCase()).test(name.toLowerCase());
    };

    const removeDots = function (str) {
        return str.replaceAll(".", "_");
    };

    const handleReleaseClick = async function (e) {
        if (releaseClicked) return;
        let params = new URLSearchParams({
            releaseId: release.id,
        });
        let result = await apiMethodCall(
            "/api/v1/release/assignees/groups?" + params,
            undefined,
            "GET"
        );
        if (result.status === "ok") {
            assigneeList = result.response;
            releaseClicked = true;
        }
    };

    onMount(() => {
        requestReleaseStats(release.name, true, false);
        stats.subscribe((val) => {
            releaseStats =
                val["releases"]?.[release.name] ?? releaseStatsDefault;
            groupStats =
                val["releases"]?.[release.name]?.["groups"] ??
                releaseStatsDefault;
        });
    });

    onDestroy(() => {
        removeReleaseRequest(release.name);
        unsub();
    });
</script>

<div class="accordion-item" class:d-none={filtered}>
    <h2 class="accordion-header" id="heading{removeDots(release.name)}">
        <button
            class="accordion-button collapsed"
            data-argus-release={release.name}
            data-bs-toggle="collapse"
            data-bs-target="#collapse{removeDots(release.name)}"
            on:click={handleReleaseClick}
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
                        {:else if releaseStats?.empty}
                            <!-- svelte-ignore empty-block -->
                        {:else if releaseStats?.dormant}
                            <!-- svelte-ignore empty-block -->
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
            <a href="/dashboard/{release.name}" class="btn btn-sm btn-dark"
                >Dashboard</a
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
                        filtered={isFiltered(group.pretty_name || group.name)}
                        parent="#accordionGroups{release.name}"
                        assigneeList={assigneeList?.[group.id] ?? []}
                        bind:runs
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
</style>
