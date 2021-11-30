<script>
    import { StatusBackgroundCSSClassMap } from "./TestStatus";
    export let stats = {
        tests: {
            "example": "failed"
        }
    };
</script>

<div class="mt-3 d-flex flex-wrap">
    {#each Object.keys(stats.tests) as test}
        <div class="d-inline-block border status-block {StatusBackgroundCSSClassMap[stats.tests[test]]}" title={test}></div>
    {/each}
</div>

<style>
    .status-block {
        width: 32px;
        height: 32px;
    }

    .status-block:hover {
        opacity: 0.5;
        cursor: help;
    }
</style>
