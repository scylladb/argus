<script>
    export let runs = [];
    import JobsList from "./JobsList.svelte";
    const filterInvestigated = function (jobs) {
        return jobs.filter(
            (job) =>
                job.investigation_status == "investigated" ||
                job.status == "passed"
        ).sort((a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime());
    };

    const filterNotInvestigated = function (jobs) {
        return jobs.filter(
            (job) =>
                job.investigation_status != "investigated" &&
                job.status != "passed"
        ).sort((a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime());
    };
</script>

<div class="container bg-white border rounded my-4 shadow-sm min-vh-100">
    <div class="row justify-content-center border-bottom">
        <h2 class="mt-2 display-6">Not Investigated</h2>
        <JobsList runs={filterNotInvestigated(runs)}/>
    </div>
    <div class="row justify-content-center">
        <h2 class="mt-2 display-6">Investigated</h2>
        <JobsList runs={filterInvestigated(runs)}/>
    </div>
</div>
