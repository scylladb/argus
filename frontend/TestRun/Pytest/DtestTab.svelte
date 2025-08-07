<script lang="ts">
    import { faEye } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import {createEventDispatcher} from "svelte";
    import {Cases} from "../Generic/Subtest";

    let { testRun } = $props();

    const dispatcher = createEventDispatcher();

</script>

<button
    class="nav-link"
    id="nav-gemini-tab-{testRun}"
    data-bs-toggle="tab"
    data-bs-target="#nav-gemini-{testRun}"
    type="button"
    role="tab"
    onclick={() => dispatcher("tab-switched", {tab: Cases.DTEST})}
    ><Fa icon={faEye}/> DTest </button
>
