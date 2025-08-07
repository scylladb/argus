<script lang="ts">
    import { onDestroy, onMount } from "svelte";
    import { sanitizeSelector } from  "../Common/TextUtils";
    import NumberStats from "../Stats/NumberStats.svelte";
    import { apiMethodCall } from "../Common/ApiUtils";
    import RunGroup from "./RunGroup.svelte";

    interface Props {
        release?: any;
        filtered?: boolean;
        runs?: any;
    }

    let { release = {
        name: "undefined",
        pretty_name: "undefined",
    }, filtered = false, runs = $bindable([]) }: Props = $props();
    let releaseStats = $state();
    let statsFetched = $state(false);

    let releaseClicked = $state(false);
    let releaseGroups = $state([]);

    let filterString = $state("");
    let assigneeList = $state({});

    const isFiltered = function (name = "") {
        if (filterString == "") {
            return false;
        }
        return !RegExp(filterString.toLowerCase()).test(name.toLowerCase());
    };

    const handleReleaseClick = async function (e) {
        releaseClicked = !releaseClicked;
        if (!releaseStats) fetchStats();
    };

    export const refreshReleaseStats = function (e) {
        statsFetched = false;
        fetchStats(true);
    };

    const fetchGroupAssignees = async function () {
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
        }
    };

    const fetchGroups = async function () {
        let params = new URLSearchParams({
            releaseId: release.id,
        });

        let res = await fetch("/api/v1/groups?" + params);
        if (res.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await res.json();
        if (json.status != "ok") {
            return Promise.reject(json.exception);
        }
        releaseGroups = json.response;
        fetchGroupAssignees();
    };

    const fetchStats = async function (forceFetch = false) {
        let params = new URLSearchParams({
            release: release.name,
            limited: new Number(false),
            force: new Number(false),
        });
        let opts = forceFetch ? {cache: "reload"} : {};
        let response = await fetch("/api/v1/release/stats/v2?" + params, opts);
        let json = await response.json();
        if (json.status != "ok") {
            return false;
        }
        releaseStats = json.response;
        statsFetched = true;
    };
</script>

<div class="accordion-item" class:d-none={filtered}>
    <h2 class="accordion-header" id="heading{sanitizeSelector(release.name)}">
        <button
            class="accordion-button collapsed"
            data-argus-release={release.name}
            data-bs-toggle="collapse"
            data-bs-target="#collapse-{release.id}"
            onclick={handleReleaseClick}
            >
                <div class="d-flex flex-column">
                    <div class="mb-1">
                        {release.pretty_name || release.name}
                    </div>
                    <div>
                        {#if releaseStats && statsFetched}
                            {#if releaseStats?.total > 0}
                                <NumberStats stats={releaseStats} />
                            {:else if releaseStats?.total == 0}
                                <!-- svelte-ignore block_empty -->
                            {/if}
                        {:else if !statsFetched && releaseClicked}
                            <span class="spinner-border spinner-border-sm"></span> Loading stats.
                        {:else}
                                <!-- svelte-ignore block_empty -->
                        {/if}
                    </div>
                </div>
            </button
        >
    </h2>
    <div
        class="accordion-collapse collapse"
        id="collapse-{release.id}"
    >
        <div class="p-2">
            <a href="/dashboard/{release.name}" class="btn btn-sm btn-dark"
                >Dashboard</a
            >
            <button class="btn btn-sm btn-dark" onclick={refreshReleaseStats}
                >Update Stats</button
            >
        </div>
        <div class="p-2 border-bottom">
            <input
                class="form-control"
                type="text"
                placeholder="Filter groups"
                bind:value={filterString}
                oninput={() => {
                    releaseGroups = releaseGroups;
                }}
            />
        </div>
        <div class="bg-light">
            <div
                class="accordion accordion-flush accordion-release-groups border-start bg-white"
                id="accordionGroups{sanitizeSelector(release.name)}"
            >
            {#if releaseClicked}
                {#await fetchGroups()}
                    <div class="row">
                        <div class="col text-center p-1">
                            <span class="spinner-border spinner-border-sm"></span> Getting groups...
                        </div>
                    </div>
                {:then}
                    {#each releaseGroups ?? [] as group (group.id)}
                        <RunGroup
                            release={release.name}
                            releaseObject={release}
                            {group}
                            filtered={isFiltered(group.pretty_name || group.name)}
                            parent="#accordionGroups{release.name}"
                            assigneeList={assigneeList?.[group.id] ?? []}
                            groupStats={releaseStats?.groups?.[group.id]}
                            bind:runs
                            on:testRunRequest
                            on:testRunRemove
                        />
                    {:else}
                        <div>No groups defined for this release!</div>
                    {/each}
                {/await}
            {/if}
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
