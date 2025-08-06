<script lang="ts">
    import { faEye } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";

    let { testRun } = $props();
</script>

<button
    class="nav-link"
    id="nav-gemini-tab-{testRun.id}"
    data-bs-toggle="tab"
    data-bs-target="#nav-gemini-{testRun.id}"
    type="button"
    role="tab"
    ><Fa icon={faEye}/> Gemini</button
>
