<script lang="ts">
    import Fa from "svelte-fa";
    import { faArrowUpRightFromSquare } from "@fortawesome/free-solid-svg-icons";
    import { byGroupAndName, matchesFilter, statusBadge, type StatusFilter } from "./summaryUtils";
    import type { SummaryTest } from "./types";

    interface Props {
        tests: SummaryTest[];
        filter: StatusFilter;
        showVersion?: boolean;
        onTestClick?: (test: SummaryTest, event: MouseEvent) => void;
    }

    let { tests, filter, showVersion = false, onTestClick }: Props = $props();

    const STATUS_ORDER = ["failed", "test_error", "error", "aborted", "running", "created", "pending", "passed"];

    const shown = $derived(
        tests
            .filter((test) => matchesFilter(test.status, filter))
            .sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || byGroupAndName(a, b)),
    );
</script>

{#if shown.length === 0}
    <div class="text-body-secondary small p-2">No tests with this status.</div>
{:else}
    <div class="table-responsive summary-scroll">
        <table class="table table-sm table-hover align-middle mb-0" aria-label="Tests">
            <thead class="sticky-top">
                <tr>
                    <th scope="col">Group</th>
                    <th scope="col">Test</th>
                    <th scope="col">Status</th>
                    {#if showVersion}<th scope="col">Version</th>{/if}
                    <th scope="col"><span class="visually-hidden">Run</span></th>
                </tr>
            </thead>
            <tbody>
                {#each shown as test (test.test_id)}
                    <tr>
                        <td class="text-body-secondary small">{test.group_name}</td>
                        <td>
                            {#if onTestClick}
                                <button
                                    type="button"
                                    class="btn btn-link btn-sm p-0 text-start"
                                    title="Add to the selected tests"
                                    onclick={(event) => onTestClick(test, event)}>{test.test_name}</button
                                >
                            {:else}
                                <span>{test.test_name}</span>
                            {/if}
                        </td>
                        <td>
                            <span class="badge {statusBadge(test.status)}">
                                {test.status.replace("_", " ")}
                            </span>
                        </td>
                        {#if showVersion}<td class="small text-body-secondary">{test.version ?? ""}</td>{/if}
                        <td class="text-end text-nowrap">
                            {#if test.build_id && test.build_number !== null}
                                <a
                                    href="/test/{test.build_id}/{test.build_number}"
                                    class="small"
                                    aria-label="Open run #{test.build_number} of {test.test_name}"
                                    title="Open run #{test.build_number}"
                                >
                                    #{test.build_number} <Fa icon={faArrowUpRightFromSquare} size="xs" />
                                </a>
                            {/if}
                        </td>
                    </tr>
                {/each}
            </tbody>
        </table>
    </div>
{/if}

<style>
    .summary-scroll {
        max-height: 28rem;
        overflow-y: auto;
    }
</style>
