<script lang="ts">
    import Fa from "svelte-fa";
    import {
        faBan,
        faCheck,
        faClock,
        faExclamation,
        faHourglassHalf,
        faSpinner,
        faXmark,
        type IconDefinition,
    } from "@fortawesome/free-solid-svg-icons";
    import { gridRows, statusBadge, type StatusFilter } from "./summaryUtils";
    import type { SummaryFamily, SummaryTest } from "./types";

    interface Props {
        family: SummaryFamily;
        filter: StatusFilter;
        onTestClick?: (test: SummaryTest, event: MouseEvent) => void;
    }

    let { family, filter, onTestClick }: Props = $props();

    const ICONS: Record<string, IconDefinition> = {
        passed: faCheck,
        failed: faXmark,
        error: faXmark,
        test_error: faExclamation,
        aborted: faBan,
        running: faSpinner,
        created: faHourglassHalf,
        pending: faClock,
    };

    const rows = $derived(gridRows(family, filter));
    const versions = $derived(family.versions.map((summary) => summary.version as string));

    const cellTitle = (version: string, cell: SummaryTest | undefined) => {
        if (!cell) return `${version}: not run`;
        if (cell.build_number === null) return `${version}: ${cell.status}`;
        return `${version}: ${cell.status}, run #${cell.build_number}`;
    };
</script>

{#if rows.length === 0}
    <div class="text-body-secondary small p-2">No tests with this status.</div>
{:else}
    <div class="table-responsive summary-scroll">
        <table class="table table-sm table-hover align-middle mb-0 w-auto grid" aria-label="Tests by version of {family.family}">
            <thead class="sticky-top">
                <tr>
                    <th scope="col" class="test-column">Test</th>
                    {#each versions as version (version)}
                        <th scope="col" class="text-center text-nowrap small">{version}</th>
                    {/each}
                </tr>
            </thead>
            <tbody>
                {#each rows as row, rowIndex (row.test.test_id)}
                    {#if rowIndex === 0 || rows[rowIndex - 1].test.group_name !== row.test.group_name}
                        <tr class="group-row">
                            <td colspan={versions.length + 1} class="small fw-semibold text-body-secondary bg-body-tertiary">
                                {row.test.group_name}
                            </td>
                        </tr>
                    {/if}
                    <tr>
                        <th scope="row" class="test-column fw-normal">
                            {#if onTestClick}
                                <button
                                    type="button"
                                    class="btn btn-link btn-sm p-0 text-start"
                                    title="Add to the selected tests"
                                    onclick={(event) => onTestClick(row.test, event)}>{row.test.test_name}</button
                                >
                            {:else}
                                <span>{row.test.test_name}</span>
                            {/if}
                        </th>
                        {#each row.cells as cell, index (versions[index])}
                            {@const title = cellTitle(versions[index], cell)}
                            <td class="text-center">
                                {#if !cell}
                                    <span class="text-body-tertiary" {title}>·</span>
                                {:else if cell.build_id && cell.build_number !== null}
                                    <a
                                        href="/test/{cell.build_id}/{cell.build_number}"
                                        class="badge cell {statusBadge(cell.status)}"
                                        {title}
                                        aria-label={title}
                                    >
                                        <Fa icon={ICONS[cell.status] ?? faClock} />
                                    </a>
                                {:else}
                                    <span class="badge cell {statusBadge(cell.status)}" {title}>
                                        <Fa icon={ICONS[cell.status] ?? faClock} />
                                    </span>
                                {/if}
                            </td>
                        {/each}
                    </tr>
                {/each}
            </tbody>
        </table>
    </div>
{/if}

<style>
    .summary-scroll {
        max-height: 32rem;
        overflow: auto;
    }

    .test-column {
        position: sticky;
        left: 0;
        z-index: 1;
        background-color: var(--bs-body-bg);
        color: var(--bs-body-color);
        min-width: 16rem;
        padding-left: 1rem;
    }

    thead .test-column {
        padding-left: 0.25rem;
    }

    td:not(:first-child),
    thead th:not(:first-child) {
        min-width: 5.5rem;
    }

    .cell {
        min-width: 1.75rem;
        text-decoration: none;
    }
</style>
