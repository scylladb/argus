<script lang="ts">
    import PaginatedTable from "./PaginatedTable.svelte";
    import type { TestRun, RunDetails } from "./Interfaces";
    import { getUser, getPicture } from "../../../Common/UserUtils";
    import { userList } from "../../../Stores/UserlistSubscriber";
    import {
        InvestigationBackgroundCSSClassMap,
        TestInvestigationStatusStrings
    } from "../../../Common/TestStatus";

    export let testRuns: TestRun[];
    export let onClose: () => void;

    let users = {};
    $: users = $userList;

    let enrichedTestRuns: TestRun[] = [];
    let loading = true;
    let error = "";

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
                const statusOrder = { failed: 0, 'test-error': 1, aborted: 2, running: 3, passed: 4 };
                const aOrder = statusOrder[a.status?.toLowerCase()] ?? 5;
                const bOrder = statusOrder[b.status?.toLowerCase()] ?? 5;
                return aOrder - bOrder || a.run_id.localeCompare(b.run_id);
            },
            width: "120px",
            render: (item: TestRun) => {
                const status = item.status?.toLowerCase();
                let badgeClass = "bg-secondary";
                let statusText = "Unknown";

                switch (status) {
                    case "failed":
                        badgeClass = "bg-danger";
                        statusText = "Failed";
                        break;
                    case "test-error":
                        badgeClass = "bg-warning";
                        statusText = "Test Error";
                        break;
                    case "passed":
                        badgeClass = "bg-success";
                        statusText = "Passed";
                        break;
                    case "aborted":
                        badgeClass = "bg-dark";
                        statusText = "Aborted";
                        break;
                    case "running":
                        badgeClass = "bg-warning text-dark";
                        statusText = "Running";
                        break;
                    default:
                        statusText = status ? status.charAt(0).toUpperCase() + status.slice(1) : "Unknown";
                }

                return `<span class="badge ${badgeClass}">${statusText}</span>`;
            },
        },
        {
            key: "start_time",
            label: "Start Time",
            sort: (a: TestRun, b: TestRun) => a.start_time - b.start_time,
            width: "130px",
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
            width: "120px",
            render: (item: TestRun) => {
                const assignee = item.assignee;
                if (!assignee || assignee === "Unassigned") {
                    return '<span class="text-muted">Unassigned</span>';
                }

                const user = getUser(assignee, users);
                const pictureUrl = getPicture(user.picture_id);
                const fullName = user.full_name || user.username || assignee;

                return `
                    <div class="d-flex align-items-center" title="${fullName}">
                        <div class="img-profile me-2" style="background-image: url(${pictureUrl});"></div>
                        <span class="text-truncate">${fullName}</span>
                    </div>
                `;
            },
        },
        {
            key: "issues",
            label: "Issues",
            sort: (a: TestRun, b: TestRun) => (a.issues?.length || 0) - (b.issues?.length || 0),
            width: "200px",
            render: (item: TestRun) => {
                if (!item.issues || item.issues.length === 0) {
                    return '<span class="text-muted">No issues</span>';
                }
                return item.issues.map(issue => {
                    const issueClass = issue.state === 'open' ? 'issue-open' : 'issue-closed';
                    return `<a href="${issue.url}" target="_blank" class="badge ${issueClass} me-1" title="${issue.title}">
                        #${issue.number}
                    </a>`;
                }).join('');
            },
        },
        {
            key: "investigation_status",
            label: "Investigation",
            sort: (a: TestRun, b: TestRun) => a.investigation_status.localeCompare(b.investigation_status),
            width: "70px",
            render: (item: TestRun) => {
                const status = item.investigation_status;
                const statusText = TestInvestigationStatusStrings[status] || status;
                const badgeClass = InvestigationBackgroundCSSClassMap[status] || "bg-secondary";

                return `
                    <span class="badge ${badgeClass}" title="${statusText}" style="width: 12px; height: 12px; border-radius: 50%; display: inline-block; cursor: help;">
                        <span class="visually-hidden">${statusText}</span>
                    </span>

                `;
            },
        },
    ];
    const sortField = "start_time";
    const sortDirection = "desc";

    // Reactive statement to fetch details when testRuns change
    $: if (testRuns) {
        fetchRunDetails();
    }
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
