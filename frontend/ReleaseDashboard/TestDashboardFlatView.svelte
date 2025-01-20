<script>
    import TestDashboardTest from "./TestDashboardTest.svelte";

    export let groupStats;
    export let assigneeList;
    export let userFilter;
    export let clickedTests;
    export let hideNotPlanned;


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
    {#each Object.entries(sortTestStats(groupStats.tests)) as [testId, testStats] (testId)}
        <TestDashboardTest {assigneeList} bind:clickedTests={clickedTests} {groupStats} {testStats} {hideNotPlanned} {userFilter} on:testClick/>
    {/each}
{/if}
