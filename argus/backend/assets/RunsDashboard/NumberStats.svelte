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
    <div
        class:d-none={stats.passed == 0}
        class="flex-fill m-0 p-1 bg-success"
    >
        {stats.passed}
    </div>
    <div
        class:d-none={stats.failed == 0}
        class="flex-fill m-0 p-1 bg-danger"
    >
        {stats.failed}
    </div>
    <div
        class:d-none={stats.running == 0}
        class="flex-fill m-0 p-1 bg-warning"
    >
        {stats.running}
    </div>
    <div
        class:d-none={stats.created == 0}
        class="flex-fill m-0 p-1 bg-info"
    >
        {stats.created}
    </div>
    <div
        class:d-none={stats.aborted == 0}
        class="flex-fill m-0 p-1 bg-dark"
    >
        {stats.aborted}
    </div>
</div>

<style>
    .cursor-question {
        cursor: help;
    }

    .text-small {
        font-size: 10pt;
    }

    .text-outline {
        color: white;
        font-weight: 500;
    }
</style>
