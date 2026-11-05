<script lang="ts">
    import { untrack } from "svelte";
    import Fa from "svelte-fa";
    import { faCheck, faChevronDown, faChevronRight, faXmark } from "@fortawesome/free-solid-svg-icons";
    import FamilyGrid from "./FamilyGrid.svelte";
    import FamilyIssues from "./FamilyIssues.svelte";
    import FamilyTimeline from "./FamilyTimeline.svelte";
    import SummaryBar from "./SummaryBar.svelte";
    import SummaryTestList from "./SummaryTestList.svelte";
    import { STATUS_GROUPS, allStatuses, issueVersions, onlyStatus, showsAll, type StatusGroup } from "./summaryUtils";
    import type { SummaryFamily, SummaryTest } from "./types";

    interface Props {
        family: SummaryFamily;
        initiallyOpen?: boolean;
        onTestClick?: (test: SummaryTest, event: MouseEvent) => void;
    }

    let { family, initiallyOpen = false, onTestClick }: Props = $props();

    const ROLLUP = "";
    let open = $state(untrack(() => initiallyOpen));
    let tab = $state<"timeline" | "grid">("timeline");
    let selected = $state(ROLLUP);
    let filter = $state(allStatuses());

    const summary = $derived(family.versions.find((version) => version.version === selected) ?? family.rollup);
    const selectedName = $derived(summary.version ?? `all of ${family.family}`);
    const issueSummary = $derived(tab === "grid" ? family.rollup : summary);
    const issueScope = $derived(issueSummary.version ?? `all of ${family.family}`);
    const counts = $derived(family.rollup.counts);
    const filterCounts = $derived(tab === "grid" ? family.rollup.counts : summary.counts);
    const total = $derived(STATUS_GROUPS.reduce((sum, { group }) => sum + counts[group], 0));
    const versionsOf = $derived(issueVersions(family));

    const select = (version: string, status?: StatusGroup) => {
        selected = version;
        filter = status ? onlyStatus(status) : allStatuses();
        open = true;
    };

    const toggleFromHeader = (event: MouseEvent) => {
        if ((event.target as Element).closest(".summary-bar")) return;
        open = !open;
    };
</script>

<section class="bg-white rounded shadow-sm family" aria-label="Family {family.family}">
    <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
    <div class="family-header p-2 rounded" class:open onclick={toggleFromHeader}>
        <button
            type="button"
            class="btn btn-sm btn-link text-decoration-none fw-semibold p-0 d-flex align-items-center gap-1"
            aria-expanded={open}
            aria-label="{open ? 'Collapse' : 'Expand'} {family.family}"
        >
            <Fa icon={open ? faChevronDown : faChevronRight} size="xs" />
            <span class="fs-6">{family.family}</span>
        </button>
        <div class="family-bar">
            <SummaryBar counts={counts} label="Results of {family.family}" onSelect={(group) => select(ROLLUP, group)} />
        </div>
        <div class="small text-body-secondary text-nowrap family-totals">
            {total} {total === 1 ? "test" : "tests"} · {counts.executed} executed
            {#if counts.pending > 0}· {counts.pending} pending{/if}
        </div>
        <div class="small text-nowrap">
            {#if counts.issues_new > 0}<span class="badge text-bg-danger">{counts.issues_new} new</span>{/if}
            {#if counts.issues_existing > 0}<span class="badge text-bg-dark">{counts.issues_existing} existing</span>{/if}
            {#if counts.issues_fixed > 0}<span class="badge text-bg-success">{counts.issues_fixed} fixed</span>{/if}
        </div>
    </div>
    {#if open}
        <div class="px-2 pb-2">
            <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
                <ul class="nav nav-pills nav-sm" role="tablist">
                    <li class="nav-item" role="presentation">
                        <button
                            type="button"
                            class="nav-link py-1 px-2"
                            class:active={tab === "timeline"}
                            role="tab"
                            aria-selected={tab === "timeline"}
                            onclick={() => (tab = "timeline")}>Timeline</button
                        >
                    </li>
                    <li class="nav-item" role="presentation">
                        <button
                            type="button"
                            class="nav-link py-1 px-2"
                            class:active={tab === "grid"}
                            role="tab"
                            aria-selected={tab === "grid"}
                            onclick={() => (tab = "grid")}>Grid</button
                        >
                    </li>
                </ul>
                <div class="d-flex flex-wrap align-items-center gap-1 ms-md-auto" role="group" aria-label="Status filter">
                    {#if !showsAll(filter)}
                        <button type="button" class="btn btn-sm btn-link" onclick={() => (filter = allStatuses())}
                            >Show all statuses</button
                        >
                    {/if}
                    {#each STATUS_GROUPS as status (status.group)}
                        <button
                            type="button"
                            class="btn btn-sm status-toggle {status.css}"
                            class:off={!filter[status.group]}
                            aria-pressed={filter[status.group]}
                            onclick={() => (filter[status.group] = !filter[status.group])}
                        >
                            <Fa icon={filter[status.group] ? faCheck : faXmark} />
                            {status.label}
                            <span class="fw-semibold ms-1">{filterCounts[status.group]}</span>
                        </button>
                    {/each}
                </div>
            </div>
            <div class="rounded bg-light-one p-2 d-flex flex-wrap gap-2">
                <div class="d-flex flex-column gap-2 main-column">
                    {#if tab === "timeline"}
                        <div class="bg-white rounded shadow-sm p-2">
                            <FamilyTimeline {family} {selected} onSelect={select} />
                        </div>
                        <div class="bg-white rounded shadow-sm p-2">
                            <h4 class="h6">Tests of {selectedName}</h4>
                            <SummaryTestList tests={summary.tests} {filter} showVersion={summary.version === null} {onTestClick} />
                        </div>
                    {:else}
                        <div class="bg-white rounded shadow-sm p-2">
                            <FamilyGrid {family} {filter} {onTestClick} />
                        </div>
                    {/if}
                </div>
                <div class="bg-white rounded shadow-sm p-2 d-flex flex-column issues-column">
                    <h4 class="h6 mb-1">Issues of {issueScope}</h4>
                    <div class="issues-fill">
                        <div class="issues-scroll">
                            <FamilyIssues summary={issueSummary} {versionsOf} />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    {/if}
</section>

<style>
    .family-header {
        display: grid;
        grid-template-columns: 8rem minmax(10rem, 32rem) auto 1fr;
        align-items: center;
        column-gap: 0.75rem;
        row-gap: 0.25rem;
        cursor: pointer;
    }

    .family-header:hover {
        background-color: var(--bs-tertiary-bg);
        color: var(--bs-body-color);
    }

    .family-totals {
        min-width: 13rem;
    }

    .status-toggle {
        border: 0;
    }

    .status-toggle.off {
        opacity: 0.45;
    }

    .status-toggle:hover,
    .status-toggle:focus-visible {
        filter: brightness(0.9);
    }

    .main-column {
        flex: 2 1 40rem;
        min-width: 0;
    }

    .issues-column {
        flex: 1 1 22rem;
        min-width: 0;
    }

    .issues-fill {
        position: relative;
        flex: 1 1 auto;
        min-height: 20rem;
    }

    .issues-scroll {
        position: absolute;
        inset: 0;
        overflow-x: hidden;
        overflow-y: auto;
    }

    @media (max-width: 767.98px) {
        .family-header {
            grid-template-columns: 8rem 1fr;
        }

        .family-totals {
            min-width: 0;
        }
    }
</style>
