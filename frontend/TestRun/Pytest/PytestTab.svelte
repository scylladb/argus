<script>
    import { faEye } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import {createEventDispatcher} from "svelte";
    import {Cases} from "../Generic/Subtest";

    export let testRun;

    const dispatcher = createEventDispatcher();

</script>

<button
    class="nav-link"
    id="nav-gemini-tab-{testRun}"
    data-bs-toggle="tab"
    data-bs-target="#nav-gemini-{testRun}"
    type="button"
    role="tab"
    on:click={() => dispatcher("tab-switched", {tab: Cases.PYTEST})}
    ><Fa icon={faEye}/> PyTest </button
>
