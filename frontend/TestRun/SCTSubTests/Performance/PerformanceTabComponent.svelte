<script lang="ts">
    import { faChartSimple } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";

    let { testRun } = $props();
</script>

<button
    class="nav-link"
    id="nav-performance-tab-{testRun.id}"
    data-bs-toggle="tab"
    data-bs-target="#nav-performance-{testRun.id}"
    type="button"
    role="tab"
    ><Fa icon={faChartSimple}/> Performance</button
>
