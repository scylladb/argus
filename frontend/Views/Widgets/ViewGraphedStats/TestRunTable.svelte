<script lang="ts">
    import PaginatedTable from "./PaginatedTable.svelte";
    import type { TestRun } from "./Interfaces";

    export let testRuns: TestRun[];
    export let onClose: () => void;

    const columns = [
        {
            key: "status",
            label: "Status",
            sort: (a: TestRun, b: TestRun) =>
                a.status === "failed" && b.status !== "failed"
                    ? -1
                    : a.status !== "failed" && b.status === "failed"
                    ? 1
                    : a.run_id.localeCompare(b.run_id),
            width: "120px",
            render: (item: TestRun) =>
                `<span class="badge bg-${item.status === "failed" ? "danger" : "success"}">${
                    item.status === "failed" ? "Failed" : "Succeeded"
                }</span>`,
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
            key: "investigation_status",
            label: "Investigation Status",
            sort: (a: TestRun, b: TestRun) => a.investigation_status.localeCompare(b.investigation_status),
        },
    ];
    const sortField = "start_time";
    const sortDirection = "desc";
</script>

<PaginatedTable items={testRuns} title="Test Runs" {columns} {sortField} {sortDirection} {onClose} />
