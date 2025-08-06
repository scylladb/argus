<script lang="ts">
    import { run as run_1 } from 'svelte/legacy';

    import PaginatedTable from "./PaginatedTable.svelte";
    import AssigneeCell from "./AssigneeCell.svelte";
    import StatusCell from "./StatusCell.svelte";
    import IssuesCell from "./IssuesCell.svelte";
    import InvestigationStatusCell from "./InvestigationStatusCell.svelte";
    import type { TestRun, RunDetails } from "./Interfaces";

    interface Props {
        testRuns: TestRun[];
        onClose: () => void;
    }

    let { testRuns, onClose }: Props = $props();

    let enrichedTestRuns: TestRun[] = $state([]);
    let loading = $state(true);
    let error = $state("");

    /**
     * Fetches detailed information for test runs including assignees and issues
     */
    async function fetchRunDetails() {
        if (!testRuns || testRuns.length === 0) {
            enrichedTestRuns = [];
            loading = false;
            return;
        }

        try {
            loading = true;
            error = "";

            const runIds = testRuns.map(run => run.run_id);
            const response = await fetch('/api/v1/views/widgets/runs_details', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ run_ids: runIds }),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (data.status !== "ok") {
                throw new Error(data.response || "Failed to fetch run details");
            }

            const runDetailsMap: Record<string, RunDetails> = data.response;

            // Merge the run details with the test runs
            enrichedTestRuns = testRuns.map(run => ({
                ...run,
                // Use status from run details if available, otherwise keep original
                status: runDetailsMap[run.run_id]?.status || run.status,
                assignee: runDetailsMap[run.run_id]?.assignee || "Unassigned",
                issues: runDetailsMap[run.run_id]?.issues || [],
            }));
        } catch (err) {
            error = `Failed to load run details: ${(err as Error).message}`;
            // Fallback to original data without enrichment
            enrichedTestRuns = testRuns.map(run => ({
                ...run,
                assignee: "Unknown",
                issues: [],
            }));
        } finally {
            loading = false;
        }
    }

    const columns = [
        {
            key: "status",
            label: "Status",
            sort: (a: TestRun, b: TestRun) => {
                const statusOrder = { failed: 0, test_error: 1, aborted: 2, running: 3, passed: 4 };
                const aOrder = statusOrder[a.status?.toLowerCase() as keyof typeof statusOrder] ?? 5;
                const bOrder = statusOrder[b.status?.toLowerCase() as keyof typeof statusOrder] ?? 5;
                return aOrder - bOrder
            },
            width: "100px",
            component: StatusCell,
        },
        {
            key: "start_time",
            label: "Start Time",
            sort: (a: TestRun, b: TestRun) => a.start_time - b.start_time,
            width: "110px",
        },
        {
            key: "duration",
            label: "Duration",
            sort: (a: TestRun, b: TestRun) => a.duration - b.duration,
            width: "130px",
        },
        {
            key: "version",
            label: "Version",
            sort: (a: TestRun, b: TestRun) => a.version.localeCompare(b.version),
            width: "130px",
        },
        {
            key: "assignee",
            label: "Assignee",
            sort: (a: TestRun, b: TestRun) => (a.assignee || "").localeCompare(b.assignee || ""),
            width: "70px",
            component: AssigneeCell,
        },
        {
            key: "issues",
            label: "Issues",
            sort: (a: TestRun, b: TestRun) => (a.issues?.length || 0) - (b.issues?.length || 0),
            component: IssuesCell,
        },
        {
            key: "investigation_status",
            label: "Investigation",
            sort: (a: TestRun, b: TestRun) => a.investigation_status.localeCompare(b.investigation_status),
            width: "70px",
            component: InvestigationStatusCell,
        },
    ];
    const sortField = "start_time";
    const sortDirection = "desc";

    // Reactive statement to fetch details when testRuns change
    run_1(() => {
        if (testRuns) {
            fetchRunDetails();
        }
    });
</script>

{#if error}
    <div class="alert alert-warning mb-3">
        {error}
    </div>
{/if}

{#if loading}
    <div class="text-center my-3">
        <div class="spinner-border spinner-border-sm" role="status">
            <span class="visually-hidden">Loading run details...</span>
        </div>
        <span class="ms-2">Loading run details...</span>
    </div>
{/if}

<PaginatedTable items={enrichedTestRuns} title="Test Runs" {columns} {sortField} {sortDirection} {onClose} />
