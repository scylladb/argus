<script>
    import { createEventDispatcher } from "svelte";

    import { StatusBackgroundCSSClassMap } from "../Common/TestStatus";
    export let stats = {
        tests: {
            example: {
                status: "failed",
                start_time: 12654364536,
            },
        },
    };
    const dispatch = createEventDispatcher();

    const handleTestClick = function (e) {
        let data = e.target.dataset;
        if (data.argusTestStartTime == 0) return;
        dispatch("testClick", {
            name: data.argusTestName,
            status: data.argusTestStatus,
            start_time: data.argusTestStartTime,
        });
    };
</script>

<div class="mt-3 d-flex flex-wrap">
    {#each Object.keys(stats.tests) as test}
        <div
            on:click|self={handleTestClick}
            class:status-block-active={stats.tests[test].start_time != 0}
            class="d-inline-block border status-block {StatusBackgroundCSSClassMap[stats.tests[test].status]}"
            data-argus-test-name={test}
            data-argus-test-status={stats.tests[test].status}
            data-argus-test-start-time={stats.tests[test].start_time}
            title={test}
        />
    {/each}
</div>

<style>
    .status-block {
        cursor: help;
        width: 32px;
        height: 32px;
    }

    .status-block-active:hover {
        opacity: 0.5;
        cursor: pointer;
    }
</style>
