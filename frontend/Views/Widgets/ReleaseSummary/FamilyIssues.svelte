<script lang="ts">
    import Fa from "svelte-fa";
    import { faGithub, faJira } from "@fortawesome/free-brands-svg-icons";
    import { faChevronDown, faChevronRight } from "@fortawesome/free-solid-svg-icons";
    import IssueCard from "../../../Common/IssueCard.svelte";
    import {
        GithubIssueColorMap,
        GithubIssueIcon,
        JiraIssueColorMap,
        JiraIssueIcon,
        getKey,
        getTitle,
        getUrl,
        isClosedInTracker,
    } from "../../../Common/IssueTypes";
    import { shortVersion } from "./summaryUtils";
    import type { Summary, SummaryIssue } from "./types";

    interface Props {
        summary: Summary;
        versionsOf: Record<string, string[]>;
    }

    let { summary, versionsOf }: Props = $props();

    let expanded: Record<string, boolean> = $state({});

    const STATE_CLASSES: Record<string, string> = { ...GithubIssueColorMap, ...JiraIssueColorMap };
    const STATE_ICONS = { ...GithubIssueIcon, ...JiraIssueIcon } as Record<string, typeof faJira>;

    const onLatestRun = (issue: SummaryIssue) => issue.status === "open";

    const byConcern = (a: SummaryIssue, b: SummaryIssue) =>
        Number(!onLatestRun(a)) - Number(!onLatestRun(b)) ||
        Number(a.novelty === "existing") - Number(b.novelty === "existing") ||
        a.key.localeCompare(b.key);

    const groups = $derived([
        { label: "Open in tracker", issues: summary.issues.filter((issue) => !isClosedInTracker(issue.state)).sort(byConcern) },
        { label: "Closed in tracker", issues: summary.issues.filter((issue) => isClosedInTracker(issue.state)).sort(byConcern) },
    ]);

    const toggleFromRow = (event: MouseEvent, id: string) => {
        if ((event.target as Element).closest("a")) return;
        expanded[id] = !expanded[id];
    };
</script>

<div class="issues">
    {#if summary.issues.length === 0}
        <div class="text-body-secondary small">No issues reproduced.</div>
    {/if}
    {#each groups as group (group.label)}
        {#if group.issues.length > 0}
            <h5 class="h6 mb-1 mt-2">{group.label} <span class="text-body-secondary">({group.issues.length})</span></h5>
            <ul class="list-unstyled mb-0" aria-label={group.label}>
                {#each group.issues as issue (issue.id)}
                    {@const versions = versionsOf[issue.id] ?? []}
                    <li class="rounded mb-1 issue-row">
                        <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
                        <div class="d-flex align-items-center gap-2 px-2 pt-1 row-head" onclick={(event) => toggleFromRow(event, issue.id)}>
                            {#if issue.state}
                                <span class="badge rounded-pill fw-normal state-pill {STATE_CLASSES[issue.state] ?? 'text-bg-secondary'}">
                                    {#if STATE_ICONS[issue.state]}<Fa icon={STATE_ICONS[issue.state]} />{/if}
                                    {issue.state}
                                </span>
                            {/if}
                            <a
                                href={getUrl(issue.issue) ?? issue.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                class="fw-semibold text-nowrap link-body-emphasis link-underline-opacity-0 link-underline-opacity-75-hover"
                            >
                                <Fa icon={issue.type === "jira" ? faJira : faGithub} />
                                {getKey(issue.issue) ?? issue.key}
                            </a>
                            <span class="text-truncate flex-grow-1 small" title={issue.title ?? ""}>
                                {getTitle(issue.issue) ?? issue.title ?? ""}
                            </span>
                            <button
                                type="button"
                                class="btn btn-sm btn-link p-0 text-body-secondary"
                                aria-expanded={!!expanded[issue.id]}
                                aria-label="Show details of {issue.key}"
                            >
                                <Fa icon={expanded[issue.id] ? faChevronDown : faChevronRight} size="xs" />
                            </button>
                        </div>
                        <div class="d-flex flex-wrap align-items-center gap-1 px-2 pb-1 small">
                            {#if onLatestRun(issue)}
                                <span class="badge text-bg-danger" title="Linked to the latest run of a test in this family"
                                    >on latest run</span
                                >
                            {:else if versions.length > 0}
                                <span class="badge text-bg-success" title="Not reproduced on a later version"
                                    >last seen {shortVersion(versions[versions.length - 1])}</span
                                >
                            {/if}
                            <span class="badge {issue.novelty === 'new' ? 'text-bg-primary' : 'text-bg-dark'}">{issue.novelty}</span>
                            {#each versions as version (version)}
                                <span class="badge text-bg-light border fw-normal" title={version}>{shortVersion(version)}</span>
                            {/each}
                        </div>
                        {#if expanded[issue.id]}
                            <div class="issue-card">
                                <IssueCard issue={issue.issue} runId="" aggregated={true} deleteEnabled={false} />
                            </div>
                        {/if}
                    </li>
                {/each}
            </ul>
        {/if}
    {/each}
</div>

<style>
    .issue-row {
        background-color: var(--bs-tertiary-bg);
    }

    .row-head {
        cursor: pointer;
        min-width: 0;
    }

    .state-pill {
        white-space: nowrap;
    }

    .issue-card :global(.row) {
        --bs-gutter-x: 0;
        margin: 0 0.25rem 0.25rem !important;
    }
</style>
