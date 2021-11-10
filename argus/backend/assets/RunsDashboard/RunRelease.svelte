<script>
    import RunGroup from "./RunGroup.svelte";
    import { releaseRequests, stats } from "./StatsSubscriber";
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
        lastStatus: "unknown",
        total: -1,
    };
    let releaseStats = releaseStatsDefault;

    releaseRequests.update(val => [...val, release.name]);
    stats.subscribe(val => {
        releaseStats = val["releases"]?.[release.name] ?? releaseStatsDefault;
    })

    const normalize = function (val, minVal, maxVal, total) {
        return ((val - minVal) / (maxVal - minVal)) * total;
    };

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
                        {#if releaseStats?.total > 0}
                            <div class="progress cursor-question" style="height: 8px" title="{
                                `Passed: ${releaseStats.passed} / Failed: ${releaseStats.failed} / Created: ${releaseStats.created} / Running: ${releaseStats.running}`}">
                                <div
                                    class="progress-bar bg-success"
                                    role="progressbar"
                                    style="width: {normalize(
                                        releaseStats.passed,
                                        0,
                                        releaseStats.total,
                                        100
                                    )}%"
                                />
                                <div
                                    class="progress-bar bg-danger"
                                    role="progressbar"
                                    style="width: {normalize(
                                        releaseStats.failed,
                                        0,
                                        releaseStats.total,
                                        100
                                    )}%"
                                />
                                <div
                                    class="progress-bar bg-warning"
                                    role="progressbar"
                                    style="width: {normalize(
                                        releaseStats.running,
                                        0,
                                        releaseStats.total,
                                        100
                                    )}%"
                                />
                                <div
                                    class="progress-bar bg-info"
                                    role="progressbar"
                                    style="width: {normalize(
                                        releaseStats.created,
                                        0,
                                        releaseStats.total,
                                        100
                                    )}%"
                                />
                            </div>
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
            {#each releaseGroups ?? [] as group}
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

    .cursor-question {
        cursor: help;
    }
</style>
