<script>
    import { faCalendar, faCheck, faSearch } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import { sendMessage } from "../Stores/AlertStore";
    import { onMount } from "svelte";
    import ProfileJobsTab from "./ProfileJobsTab.svelte";
    import { TestInvestigationStatus } from "../Common/TestStatus";
    export let jobs;
    export let userId;

    let activeTab = "todo";
    let jobsToDo = [];
    let jobsDone = [];

    const fetchUserJobs = async function() {
        if (jobs) {
            prepareJobs(jobs);
            jobs = undefined;
            return;
        }

        try {
            let response = await fetch(userId ? `/api/v1/team/user/${userId}/jobs` :"/api/v1/user/jobs");
            if (response.status != 200) throw new Error("HTTP Transport Error");
            let json = await response.json();
            if (json.status != "ok") throw new Error(`API Error: ${json.exception.arguments.join(" ")}`);
            prepareJobs(json.response);
        } catch (e) {
            if (e instanceof Error) {
                sendMessage("error", `Error fetching user jobs\n${e.message}`, "ProfileJob::testInfo");
            } else {
                sendMessage("error", "Error fetching user jobs\nUnknown error. Check console for details", "ProfileJobs::testInfo");
            }
            console.log(e);
        }
    };

    const prepareJobs = function(jobs) {
        jobsToDo = jobs.filter(v => v.investigation_status != "investigated" && v.status != "passed" && v.investigation_status != "ignored");
        jobsDone = jobs.filter(v => ["investigated", "ignored"].includes(v.investigation_status) || v.status == "passed");
    };

    const handleInvestigationStatusChangeToDo = async function(e) {
        let runId = e.detail.runId;
        let status = e.detail.status;
        if (status != TestInvestigationStatus.INVESTIGATED) return;
        let investigatedJob = jobsToDo.find(v => v.id == runId);
        jobsDone.push(investigatedJob);
        jobsDone = jobsDone;
        jobsToDo = jobsToDo.filter(v => v.id != runId);
    };

    const handleInvestigationStatusChangeDone = async function(e) {
        let runId = e.detail.runId;
        let status = e.detail.status;
        if (status == TestInvestigationStatus.INVESTIGATED || status == TestInvestigationStatus.IGNORED) return;
        let investigatedJob = jobsDone.find(v => v.id == runId);
        jobsToDo.push(investigatedJob);
        jobsToDo = jobsToDo;
        jobsDone = jobsDone.filter(v => v.id != runId);
    };

    const handleBatchIgnore = function() {
        fetchUserJobs();
    };


    onMount(async () => {
        await fetchUserJobs();
    });
</script>
<div class="container">
    <div class="bg-white rounded my-4 border-start border-end border-bottom ">
        <div class="d-flex btn-group p-2">
                <button
                    class="btn btn-dark"
                    class:active={activeTab == "todo"}
                    on:click={() => (activeTab = "todo")}
                >
                    <Fa icon={faSearch}/> To Do
                </button>
                <button
                    class="btn btn-dark"
                    class:active={activeTab == "done"}
                    on:click={() => (activeTab = "done")}
                >
                    <Fa icon={faCheck}/> Done
                </button>
                <button
                    class="btn btn-dark"
                    class:active={activeTab == "planned"}
                    on:click={() => (activeTab = "planned")}
                >
                    <Fa icon={faCalendar}/> Planned
                </button>
        </div>
        <div class="p-2">
            <div class="bg-light-one rounded p-2">
                <div class:d-none={activeTab != "todo"}>
                    <ProfileJobsTab jobs={jobsToDo} on:investigationStatusChange={handleInvestigationStatusChangeToDo} on:batchIgnoreDone={handleBatchIgnore}/>
                </div>
                <div class:d-none={activeTab != "done"}>
                    <ProfileJobsTab jobs={jobsDone} on:investigationStatusChange={handleInvestigationStatusChangeDone} on:batchIgnoreDone={handleBatchIgnore}/>
                </div>
                <div class:d-none={activeTab != "planned"}>
                    WIP
                </div>
            </div>
        </div>
    </div>
</div>


<style>

</style>
