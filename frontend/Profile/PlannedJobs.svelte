<script module lang="ts">

    export interface PlannedTest {
        id: string,
        name: string,
        pretty_name: string,
        build_system_id: string,
        last_run: LastRun,
        build_system_url: string,
    }

    export interface LastRun {
        status: string,
        investigation_status: string,
        build_id: string,
        start_time: string,
        assignee: string,
    }

    export const STATUS_SORT_ORDER = {
        [TestStatus.NOT_RUN]: 0,
        [TestStatus.FAILED]: 1,
        [TestStatus.TEST_ERROR]: 2,
        [TestStatus.ABORTED]: 3,
        [TestStatus.PASSED]: 4,
        [TestStatus.RUNNING]: 5,
        [TestStatus.CREATED]: 6,
        [TestStatus.NOT_PLANNED]: 7,
    };
</script>

<script lang="ts">
    import { onMount } from "svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import PlannedJob from "./PlannedJob.svelte";
    import { TestStatus } from "../Common/TestStatus";

    let plannedTests: PlannedTest[] = $state([]);
    interface Props {
        jobCount?: number;
    }

    let { jobCount = $bindable(0) }: Props = $props();
    let fetching = $state(false);
    let pageSize = $state(10);

    const sortJobs = function (a: PlannedTest, b: PlannedTest) {
        const lhs = STATUS_SORT_ORDER[a?.last_run?.status || TestStatus.NOT_RUN];
        const rhs = STATUS_SORT_ORDER[b?.last_run?.status || TestStatus.NOT_RUN];

        return lhs - rhs;
    };

    const fetchPlannedJobs = async function() {
        try {
            fetching = true;
            let response = await fetch("/api/v1/user/planned_jobs");
            if (response.status != 200) throw new Error("HTTP Transport Error");
            let json = await response.json();
            if (json.status != "ok") throw new Error(`API Error: ${json.response.arguments.join(" ")}`);

            plannedTests = json.response.sort(sortJobs);
            jobCount = plannedTests.filter(t => !t.last_run).length;
        } catch (e) {
            if (e instanceof Error) {
                sendMessage("error", `Error fetching planned user jobs\n${e.message}`, "ProfileJob::testInfo");
            } else {
                sendMessage("error", "Error fetching planned user jobs\nUnknown error. Check console for details", "ProfileJobs::testInfo");
            }
            console.log(e);
        } finally {
            fetching = false;
        }
    };

    onMount(async () => {
        await fetchPlannedJobs();
    });

</script>


<div>
    {#if !fetching}
        {#each plannedTests.slice(0, pageSize) as test (test.id)}
            <PlannedJob test={test} />
        {:else}
            <div class="text-muted text-center p-4">
                No jobs planned.
            </div>
        {/each}
    {:else}
        <div class="text-center p-4">
            <span class="spinner-border spinner-border-sm"></span> Getting jobs...
        </div>
    {/if}
    {#if plannedTests.length > pageSize}
        <div>
            <button class="btn btn-primary d-block w-100" onclick={() => pageSize += pageSize}>
                Load More...
            </button>
        </div>
    {/if}
</div>
