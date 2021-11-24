<script>
    import RunGroup from "./RunGroup.svelte";
    import { releaseRequests, stats } from "./StatsSubscriber";
    import ProgressBarStats from "./ProgressBarStats.svelte";
    import NumberStats from "./NumberStats.svelte";
    let releaseGroups = [];
    export let release = {
        name: "undefined",
        pretty_name: "undefined",
    };
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

    const sortGroupsByStatus = function() {
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

    releaseRequests.update(val => [...val, release.name]);
    stats.subscribe(val => {
        releaseStats = val["releases"]?.[release.name] ?? releaseStatsDefault;
        groupStats = val["releases"]?.[release.name]?.["groups"] ?? releaseStatsDefault;
        sortGroupsByStatus();
    })


    const removeDots = function (str) {
        return str.replaceAll(".", "_");
    };

    const fetchGroupsForRelease = function (e) {
        if (fetched) return;

        fetch("/api/v1/release_groups", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                release: release,
            }),
        })
            .then((res) => {
                if (res.status == 200) {
                    return res.json();
                } else {
                    console.log("Error fetching groups");
                }
            })
            .then((res) => {
                if (res.status === "ok") {
                    releaseGroups = res.response;
                    sortGroupsByStatus();
                    fetched = true;
                } else {
                    console.log("Response returned an error");
                    console.log(res.response);
                }
            });
    };
</script>

<div class="accordion-item">
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
                        {#if (releaseStats?.total) > 0}
                            <NumberStats stats={releaseStats} />
                        {:else if releaseStats?.total == -1}
                            <span class="spinner-border spinner-border-sm"></span>
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
        <div
            class="accordion accordion-flush accordion-release-groups border-start"
            id="accordionGroups{removeDots(release.name)}"
        >
            {#each releaseGroups ?? [] as group (group.id)}
                <RunGroup
                    release={release.name}
                    {group}
                    parent="#accordionGroups{release.name}"
                    on:testRunRequest
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
