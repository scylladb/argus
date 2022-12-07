<script>
    import { filterInvestigated, filterNotInvestigated } from "../Common/RunUtils";
    export let runs = [];
    import JobsList from "./JobsList.svelte";

</script>

<div class="container-fluid bg-white border rounded my-4 shadow-sm">
    <div class="row justify-content-center border-bottom mb-2">
        <h2 class="mt-2 display-6">Not Investigated</h2>
        <JobsList runs={filterNotInvestigated(runs)}/>
    </div>
    <div class="row justify-content-center mb-2">
        <h2 class="mt-2 display-6">Investigated</h2>
        <JobsList runs={filterInvestigated(runs)}/>
    </div>
</div>
