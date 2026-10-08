<script lang="ts">
    import Fa from "svelte-fa";
    import { faCheck, faMagnifyingGlass, faPlay, faXmark } from "@fortawesome/free-solid-svg-icons";
    import { StatusBackgroundCSSClassMap, StatusSortPriority } from "../../Common/TestStatus";
    import type { StatusCounts, StatusName } from "./sidebarSort";

    interface Props {
        stats: StatusCounts;
    }

    let { stats }: Props = $props();

    const STATUS_LABELS: Record<StatusName, string> = {
        failed: "failed",
        test_error: "test error",
        error: "error",
        aborted: "aborted",
        passed: "passed",
        running: "running",
        created: "created",
        not_run: "not run",
        not_planned: "not planned",
        unknown: "unknown",
    };

    const statuses = (Object.keys(STATUS_LABELS) as StatusName[]).toSorted(
        (left, right) => StatusSortPriority[left] - StatusSortPriority[right]
    );

    const segments = $derived(
        statuses
            .filter((status) => (stats[status] ?? 0) > 0)
            .map((status) => ({ status, count: stats[status] ?? 0, width: ((stats[status] ?? 0) / stats.total) * 100 }))
    );
    const failed = $derived((stats.failed ?? 0) + (stats.test_error ?? 0) + (stats.error ?? 0));
    const label = $derived(
        [
            ...segments.map((segment) => `${segment.count} ${STATUS_LABELS[segment.status]}`),
            ...(stats.to_investigate ? [`${stats.to_investigate} to investigate`] : []),
        ].join(", ") + ` of ${stats.total}`
    );
</script>

{#if stats.total > 0}
    <div class="d-flex align-items-center gap-2 w-100" role="img" aria-label={label} title={label}>
        <div class="status-bar d-flex flex-grow-1 rounded-pill overflow-hidden">
            {#each segments as segment (segment.status)}
                <div class={StatusBackgroundCSSClassMap[segment.status]} style:width="{segment.width}%"></div>
            {/each}
        </div>
        <div class="d-flex align-items-center gap-2 small text-nowrap">
            {#if failed > 0}
                <span class="text-danger-emphasis"><Fa icon={faXmark} /> {failed}</span>
            {/if}
            {#if stats.running}
                <span class="text-warning-emphasis"><Fa icon={faPlay} /> {stats.running}</span>
            {/if}
            {#if stats.passed}
                <span class="text-success-emphasis"><Fa icon={faCheck} /> {stats.passed}</span>
            {/if}
            {#if stats.to_investigate}
                <span class="badge text-bg-danger"><Fa icon={faMagnifyingGlass} /> {stats.to_investigate}</span>
            {/if}
        </div>
    </div>
{/if}

<style>
    .status-bar {
        height: 6px;
        min-width: 3rem;
        background-color: var(--bs-secondary-bg);
    }
</style>
