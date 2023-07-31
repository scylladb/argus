<script>
    export let testRun;
</script>

<button
    class="nav-link"
    id="nav-performance-tab-{testRun.id}"
    data-bs-toggle="tab"
    data-bs-target="#nav-performance-{testRun.id}"
    type="button"
    role="tab"
    ><i class="fas fa-chart-simple" /> Performance</button
>