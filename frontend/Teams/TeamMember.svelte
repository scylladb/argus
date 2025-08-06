<script lang="ts">
    import { faEye } from "@fortawesome/free-regular-svg-icons";
    import { faCircle, faEyeSlash, faFolderOpen } from "@fortawesome/free-solid-svg-icons";
    import format from "string-template";
    import { onMount } from "svelte";
    import Fa from "svelte-fa";
    import { StatusCSSClassMap, TestInvestigationStatus, TestStatus } from "../Common/TestStatus";
    import { getPicture } from "../Common/UserUtils";
    import ProfileJobs from "../Profile/ProfileJobs.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { TeamManagerAPIError, TeamManagerException, TeamRoutes, type Member, type RawUserJobsResponse, type ShortJob } from "./TeamUtils";
    interface Props {
        member: Member;
    }

    let { member }: Props = $props();
    let userJobs: ShortJob[] = $state();
    let failed = $state(false);
    let requestedDetail = $state(false);
    let showInvestigatedDetailedStats = $state(false);
    let showNotInvestigatedDetailedStats = $state(false);

    const fetchUserJobs = async function() {
        try {
            const response = await fetch(format(TeamRoutes.GET_JOBS_FOR_USER, { userId: member.id }));
            if (!response.ok) {
                throw new TeamManagerException(`HTTP Transport Error: ${response.status}`);
            }
            const json: RawUserJobsResponse = await response.json();
            if (json.status === "ok") {
                userJobs = json.response;
            } else {
                throw new TeamManagerAPIError(json.response);
            }
        } catch (error) {
            sendMessage("error", `Failed to fetch jobs for a user ${member.full_name}`, "TeamMember::fetchUserJobs");
            console.log(error);
            failed = true;
        }
    };

    interface IJobStats {
        [key: string]: number,
        total: number,
        passed: number,
        failed: number,
        aborted: number,
        running: number,
        created: number,
    }

    const aggregateJobs = function(jobs: ShortJob[], predicate: (job: ShortJob) => boolean): IJobStats{
        let filteredJobs = jobs.filter(predicate);
        let result: IJobStats = {
            total: 0,
            passed: 0,
            failed: 0,
            aborted: 0,
            running: 0,
            created: 0,
        };
        filteredJobs.forEach((job) => {
            result[job.status] += 1;
            result.total += 1;
        });

        return result;
    };

    onMount(() => {
        fetchUserJobs();
    });
</script>


<div class="d-flex p-2 align-items-center rounded shadow-sm mb-2 bg-white">
    <img class="img-thumb" src="{getPicture(member.picture_id)}" alt="{member.full_name}">
    <div class="ms-2">
        <div>{member.full_name}</div>
        <div class="text-muted">{member.username}</div>
    </div>
    {#if userJobs}
        <div class="ms-auto d-flex border p-1 rounded">
            {#await aggregateJobs(userJobs, (job) => job.investigation_status == TestInvestigationStatus.NOT_INVESTIGATED && job.status != TestStatus.PASSED) then stats}
                <div class="px-2" role="button" class:border-end={showNotInvestigatedDetailedStats} onclick={() => (showNotInvestigatedDetailedStats = !showNotInvestigatedDetailedStats)}>
                    <Fa icon={faEyeSlash} /> {stats.total}
                </div>
                <div class:d-flex={showNotInvestigatedDetailedStats} class:d-none={!showNotInvestigatedDetailedStats}>
                    <div class="ms-2">
                        <Fa icon={faCircle} class="{StatusCSSClassMap.failed}"/> {stats.failed}
                    </div>
                    <div class="ms-2">
                        <Fa icon={faCircle} class="{StatusCSSClassMap.running}"/> {stats.running}
                    </div>
                    <div class="ms-2">
                        <Fa icon={faCircle} class="{StatusCSSClassMap.created}"/> {stats.created}
                    </div>
                    <div class="ms-2">
                        <Fa icon={faCircle} class="{StatusCSSClassMap.aborted}"/> {stats.aborted}
                    </div>
                    <div class="ms-2">
                        <Fa icon={faCircle} class="{StatusCSSClassMap.passed}"/> {stats.passed}
                    </div>
                </div>
            {/await}
        </div>
        <div class="ms-2 d-flex border p-1 rounded">
            {#await aggregateJobs(userJobs, (job) => job.investigation_status == TestInvestigationStatus.INVESTIGATED || job.status == TestStatus.PASSED) then stats}
                <div class="px-2" class:border-end={showInvestigatedDetailedStats} role="button" onclick={() => (showInvestigatedDetailedStats = !showInvestigatedDetailedStats)}>
                    <Fa icon={faEye} /> {stats.total}
                </div>
                <div class:d-flex={showInvestigatedDetailedStats} class:d-none={!showInvestigatedDetailedStats}>
                    <div class="ms-2">
                        <Fa icon={faCircle} class="{StatusCSSClassMap.failed}"/> {stats.failed}
                    </div>
                    <div class="ms-2">
                        <Fa icon={faCircle} class="{StatusCSSClassMap.running}"/> {stats.running}
                    </div>
                    <div class="ms-2">
                        <Fa icon={faCircle} class="{StatusCSSClassMap.created}"/> {stats.created}
                    </div>
                    <div class="ms-2">
                        <Fa icon={faCircle} class="{StatusCSSClassMap.aborted}"/> {stats.aborted}
                    </div>
                    <div class="ms-2">
                        <Fa icon={faCircle} class="{StatusCSSClassMap.passed}"/> {stats.passed}
                    </div>
                </div>
            {/await}
        </div>
    {:else}
        {#if failed}
            <div class="ms-auto">Fetching jobs failure.</div>
        {:else}
            <div class="ms-auto">
                Fetching...
            </div>
        {/if}
    {/if}
    <button
        class="ms-2 btn btn-sm btn-primary"
        data-bs-toggle="collapse"
        data-bs-target="#showAllJobs-{member.id}"
        onclick={() => requestedDetail = !requestedDetail}
    >
        <Fa icon={faFolderOpen}/>
    </button>
</div>
<div id="showAllJobs-{member.id}" class="collapse">
    {#if requestedDetail && userJobs}
        <ProfileJobs jobs={userJobs} userId={member.id} />
    {/if}
</div>

<style>
    .img-thumb {
        border-radius: 50%;
        width: 64px;
    }
</style>
