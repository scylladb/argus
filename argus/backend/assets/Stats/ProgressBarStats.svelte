<script>
    export let stats = {};

    const normalize = function (val, minVal, maxVal, total) {
        return ((val - minVal) / (maxVal - minVal)) * total;
    };
</script>

<div
    class="progress cursor-question"
    style="height: 8px"
    title={`Passed: ${stats.passed} / Failed: ${stats.failed} / Created: ${stats.created} / Running: ${stats.running}`}
>
    <div
        class="progress-bar bg-success"
        role="progressbar"
        style="width: {normalize(stats.passed, 0, stats.total, 100)}%"
    />
    <div
        class="progress-bar bg-danger"
        role="progressbar"
        style="width: {normalize(stats.failed, 0, stats.total, 100)}%"
    />
    <div
        class="progress-bar bg-warning"
        role="progressbar"
        style="width: {normalize(stats.running, 0, stats.total, 100)}%"
    />
    <div
        class="progress-bar bg-info"
        role="progressbar"
        style="width: {normalize(stats.created, 0, stats.total, 100)}%"
    />
</div>

<style>
    .cursor-question {
        cursor: help;
    }
</style>
