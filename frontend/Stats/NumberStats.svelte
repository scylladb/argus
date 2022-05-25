<script>
    import { TestStatus, StatusBackgroundCSSClassMap } from "../Common/TestStatus";
    import { titleCase, subUnderscores } from "../Common/TextUtils";
    export let stats = {
        created: 0,
        running: 0,
        passed: 0,
        failed: 0,
        lastStatus: "unknown",
        total: -1,
    };
</script>

<div
    class="shadow-sm overflow-hidden border rounded d-flex p-0 m-0 cursor-question text-small text-center text-light text-outline"
    title="Total: {stats.total}"
>
    {#each Object.values(TestStatus) as status}
        {#if stats[status]}
            <div class:d-none={stats[status] == 0} class="flex-fill m-0 p-1 {StatusBackgroundCSSClassMap[status]}" title={subUnderscores(titleCase(status))}>
                {stats[status]}
            </div>
        {/if}
    {/each}
</div>

<style>
    .cursor-question {
        cursor: help;
    }

    .text-small {
        font-size: 0.75em;
    }

    .text-outline {
        color: white;
        font-weight: 500;
    }
    .bg-gray {
        background-color: #dddddd;
    }
</style>
