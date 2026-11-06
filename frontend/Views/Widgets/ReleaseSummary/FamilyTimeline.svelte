<script lang="ts">
    import SummaryBar from "./SummaryBar.svelte";
    import { STATUS_GROUPS, type StatusGroup } from "./summaryUtils";
    import type { Summary, SummaryFamily } from "./types";

    interface Props {
        family: SummaryFamily;
        selected: string;
        onSelect: (version: string, status?: StatusGroup) => void;
    }

    let { family, selected, onSelect }: Props = $props();

    const ROLLUP = "";
    const rows = $derived([
        { key: ROLLUP, name: `All of ${family.family}`, summary: family.rollup },
        ...family.versions.map((summary: Summary) => ({ key: summary.version as string, name: summary.version as string, summary })),
    ]);
</script>

<div class="table-responsive">
    <table class="table table-sm align-middle mb-2 timeline" aria-label="Versions of {family.family}">
        <thead>
            <tr>
                <th scope="col">Version</th>
                <th scope="col" class="w-25">Tests</th>
                {#each STATUS_GROUPS as status (status.group)}
                    <th scope="col" class="text-end">{status.label}</th>
                {/each}
                <th scope="col" class="text-end">Issues</th>
            </tr>
        </thead>
        <tbody>
            {#each rows as row (row.key)}
                {@const isSelected = selected === row.key}
                <tr class:table-active={isSelected} class:fw-semibold={row.key === ROLLUP}>
                    <th scope="row" class="fw-normal">
                        <button
                            type="button"
                            class="btn btn-link btn-sm p-0 text-nowrap"
                            class:fw-semibold={row.key === ROLLUP}
                            aria-pressed={isSelected}
                            onclick={() => onSelect(row.key)}>{row.name}</button
                        >
                    </th>
                    <td>
                        <SummaryBar
                            counts={row.summary.counts}
                            label="Results of {row.name}"
                            onSelect={(group: StatusGroup) => onSelect(row.key, group)}
                        />
                    </td>
                    {#each STATUS_GROUPS as status (status.group)}
                        {@const count = row.summary.counts[status.group]}
                        <td class="text-end">
                            {#if count > 0}
                                <button
                                    type="button"
                                    class="btn btn-link btn-sm p-0"
                                    aria-label="Show the {count} {status.label.toLowerCase()} tests of {row.name}"
                                    onclick={() => onSelect(row.key, status.group)}>{count}</button
                                >
                            {:else}
                                <span class="text-body-tertiary">0</span>
                            {/if}
                        </td>
                    {/each}
                    <td class="text-end text-nowrap small">
                        {#if row.summary.counts.issues_new > 0}
                            <span class="badge text-bg-danger" title="New issues">{row.summary.counts.issues_new} new</span>
                        {/if}
                        {#if row.summary.counts.issues_existing > 0}
                            <span class="badge text-bg-dark" title="Existing issues">{row.summary.counts.issues_existing} existing</span>
                        {/if}
                        {#if row.summary.counts.issues_fixed > 0}
                            <span class="badge text-bg-success" title="Fixed issues">{row.summary.counts.issues_fixed} fixed</span>
                        {/if}
                    </td>
                </tr>
            {/each}
        </tbody>
    </table>
</div>
