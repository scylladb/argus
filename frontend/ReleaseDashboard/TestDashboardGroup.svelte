<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import NumberStats from "../Stats/NumberStats.svelte";
    import { getPicture } from "../Common/UserUtils";
    import Fa from "svelte-fa";
    import { faArrowDown, faArrowUp } from "@fortawesome/free-solid-svg-icons";
    import TestDashboardTest from "./TestDashboardTest.svelte";

    interface Props {
        stats: any;
        groupStats: any;
        collapsed: any;
        filtered?: boolean;
        dashboardObjectType?: string;
        assigneeList: any;
        users: any;
        doFilters: any;
        clickedTests: any;
    }

    let {
        stats,
        groupStats,
        collapsed,
        filtered = false,
        dashboardObjectType = "release",
        assigneeList,
        users,
        doFilters,
        clickedTests = $bindable()
    }: Props = $props();

    const dispatch = createEventDispatcher();


    const sortTestStats = function (testStats) {
        const testPriorities = {
            failed: 6,
            passed: 5,
            running: 4,
            created: 3,
            aborted: 2,
            not_run: 1,
            not_planned: 0,
            unknown: -1,

        };
        let tests = Object.values(testStats)
            .sort((a, b) => testPriorities[b.status] - testPriorities[a.status] || a.test.name.localeCompare(b.test.name))
            .reduce((tests, testStats) => {
                tests[testStats.test.id] = testStats;
                return tests;
            }, {});
        return tests;
    };
</script>

{#if !groupStats.disabled}
    <div class="p-2 shadow mb-2 rounded bg-main" class:d-none={filtered}>
        <h5 class="mb-2 d-flex">
            <div class="flex-fill">
                <div class="mb-2">{#if dashboardObjectType != "release"}<span class="d-inline-block border p-1 me-1">{stats.releases?.[groupStats.group.release_id]?.name ?? "" }</span>{/if}{groupStats.group.pretty_name || groupStats.group.name}</div>
                <div class="mb-2">
                    <NumberStats displayInvestigations={true} stats={groupStats} displayPercentage={true} on:quickSelect/>
                </div>
                {#if Object.keys(assigneeList.groups).length > 0 && Object.keys(users).length > 0}
                    <div class="shadow-sm bg-main rounded d-inline-block p-2">
                        <div class="d-flex align-items-center">
                            <img
                                class="img-thumb ms-2"
                                src={getPicture(
                                    users[assigneeList.groups[groupStats.group.id]?.[0]]
                                        ?.picture_id
                                )}
                                alt=""
                            />
                            <span class="ms-2 fs-6"
                                >{users[assigneeList.groups[groupStats.group.id]?.[0]]
                                    ?.full_name ?? "unassigned"}</span
                            >
                        </div>
                    </div>
                {/if}
            </div>
            <div class="ms-auto">
                <button
                    class="btn btn-sm"
                    data-bs-toggle="collapse"
                    data-bs-target="#collapse-{groupStats.group.id}"
                    onclick={() => {
                        dispatch("toggleCollapse", `collapse-${groupStats.group.id}`);
                    }}
                >
                {#if collapsed}
                    <Fa icon={faArrowDown}/>
                {:else}
                    <Fa icon={faArrowUp}/>
                {/if}
                </button>
            </div>
        </h5>
        <div class="collapse" class:show={!collapsed} id="collapse-{groupStats.group.id}">
            <div id="testContainer-{groupStats.group.id}" class="my-2 d-flex flex-wrap bg-lighter rounded shadow-sm">
                {#each Object.entries(sortTestStats(groupStats.tests)) as [testId, testStats] (testId)}
                    <TestDashboardTest {assigneeList} bind:clickedTests={clickedTests} {groupStats} {testStats} {doFilters} on:testClick/>
                {:else}
                    <div class="text-dark m-2">No tests for this group</div>
                {/each}
            </div>
        </div>
    </div>
{/if}

<style>
    .img-thumb {
        border-radius: 50%;
        width: 32px;
    }

</style>
