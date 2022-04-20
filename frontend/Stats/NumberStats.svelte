<script>
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
    <div class:d-none={stats.passed == 0} class="flex-fill m-0 p-1 bg-success" title="Passed">
        {stats.passed}
    </div>
    <div class:d-none={stats.failed == 0} class="flex-fill m-0 p-1 bg-danger" title="Failed">
        {stats.failed}
    </div>
    <div class:d-none={stats.running == 0} class="flex-fill m-0 p-1 bg-warning" title="Running">
        {stats.running}
    </div>
    <div class:d-none={stats.created == 0} class="flex-fill m-0 p-1 bg-info" title="Created">
        {stats.created}
    </div>
    <div class:d-none={stats.aborted == 0} class="flex-fill m-0 p-1 bg-dark" title="Aborted">
        {stats.aborted}
    </div>
    <div class:d-none={stats.not_run == 0} class="flex-fill m-0 p-1 bg-gray text-dark" title="Not run">
        {stats.not_run}
    </div>
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
