<script>
    import { faEye } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";

    export let testRun;
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
