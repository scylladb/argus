<script lang="ts">
    import PaginatedTable from "./PaginatedTable.svelte";
    import StackTracePreview from "./StackTracePreview.svelte";
    import StatusBadge from "./StatusBadge.svelte";
    import type { NemesisData } from "./Interfaces";

    interface Props {
        nemesisName: string | null;
        nemesisData: NemesisData[];
        onClose: () => void;
    }

    let { nemesisName, nemesisData, onClose }: Props = $props();

    let items = $derived(nemesisName ? nemesisData.filter((n) => n.name === nemesisName) : []);

    const columns = [
        {
            key: "status",
            label: "Status",
            sort: (a: NemesisData, b: NemesisData) =>
                a.status === "failed" && b.status !== "failed"
                    ? -1
                    : a.status !== "failed" && b.status === "failed"
                    ? 1
                    : a.run_id.localeCompare(b.run_id),
            width: "120px",
            component: StatusBadge,
        },
        {
            key: "start_time",
            label: "Start Time",
            sort: (a: NemesisData, b: NemesisData) => a.start_time - b.start_time,
            width: "150px",
        },
        {
            key: "duration",
            label: "Duration",
            sort: (a: NemesisData, b: NemesisData) => a.duration - b.duration,
            width: "130px",
        },
        {
            key: "version",
            label: "Version",
            sort: (a: NemesisData, b: NemesisData) => a.version.localeCompare(b.version),
            width: "130px",
        },
        { key: "stack_trace", label: "Stack Trace", component: StackTracePreview },
    ];
    const sortField = "status";
    const sortDirection = "asc";
</script>

{#if nemesisName}
    <PaginatedTable {items} title={`Nemesis: ${nemesisName}`} {sortField} {sortDirection} {columns} {onClose} />
{/if}
