<script>
    import { faChartSimple } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";

    export let testRun;
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
