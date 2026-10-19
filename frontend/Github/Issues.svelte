<script module lang="ts">
    // Re-export all shared types and helpers from IssueTypes.ts so existing importers of
    // Issues.svelte continue to work without changes.
    export type {
        GithubState,
        JiraState,
        State,
        Label,
        Link,
        Issue,
        GithubSubtype,
        JiraSubtype,
        TestRun,
        RichAssignee,
    } from "../Common/IssueTypes";
    export {
        getTitle,
        getRepo,
        getNumber,
        getUrl,
        getAssignees,
        getKey,
        getAssigneesRich,
        label2color,
    } from "../Common/IssueTypes";
</script>

<script lang="ts">
    import { PLUGIN_NAMES } from "../Common/PluginNames";
    import { newIssueDestinations } from "../Common/IssueDestinations";
    import { sendMessage } from "../Stores/AlertStore";
    import { faCheck, faChevronDown, faChevronUp, faCopy } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import IssuesCopyModal from "./IssuesCopyModal.svelte";
    import queryString from 'query-string';
    import IssueCard from "../Common/IssueCard.svelte";
    import type { Issue, GithubSubtype, JiraSubtype, Label } from "../Common/IssueTypes";
    import { getTitle, getRepo, label2color, labelTextColor, priorityIndex, priorityRank } from "../Common/IssueTypes";
    import { untrack } from "svelte";
    import { SvelteSet } from "svelte/reactivity";
    interface Props {
        id?: string;
        runId: any;
        testId: any;
        pluginName: any;
        filter_key?: string;
        submitDisabled?: boolean;
        aggregateByIssue?: boolean;
        productVersion?: string;
        includeNoVersion?: boolean;
    }

    let {
        id = "",
        runId,
        testId,
        pluginName,
        filter_key = "run_id",
        submitDisabled = false,
        aggregateByIssue = false,
        productVersion = undefined,
        includeNoVersion = false,
    }: Props = $props();
    let newIssueUrl = $state("");
    let issues: Issue[] = $state([]);
    let fetching = $state(false);
    let showAllLabels = $state(false);
    export const fetchIssues = async function () {
        fetching = true;
        try {
            let queryParams: Record<string, any> = {
                filterKey: filter_key,
                id: id,
                aggregateByIssue: new Number(aggregateByIssue),
            };
            if (productVersion) {
                queryParams.productVersion = productVersion;
                if (includeNoVersion) {
                    queryParams.includeNoVersion = 1;
                }
            }
            let params = queryString.stringify(queryParams).toString();
            let apiResponse = await fetch("/api/v1/issues/get?" + params);
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                issues = apiJson.response;
                fetching = false;
            } else {
                throw apiJson;
            }
        } catch (error) {
            console.log(error);
        }
    };

    type SortCriteria = "name" | "repo" | "date" | "priority";
    type FilterGroup = "state" | "priority" | "project";
    const NO_PRIORITY = "";
    const uid = $props.id();

    let sortCriteria: SortCriteria = $state("date");
    let reverseSort = $state(true);
    let currentPage = $state(0);
    let PAGE_SIZE = $state(10);
    let filterString = $state("");
    let selectedLabels: Label[] = $state([]);
    const excluded: Record<FilterGroup, SvelteSet<string>> = { state: new SvelteSet(), priority: new SvelteSet(), project: new SvelteSet() };

    const jiraIssues = $derived(issues.filter((issue) => issue.subtype === "jira") as JiraSubtype[]);
    const distinct = (values: string[]) => [...new Set(values)].sort();
    const optionLabel = (value: string) => (value === NO_PRIORITY ? "no priority" : value);
    const filterOptions: Record<FilterGroup, string[]> = $derived({
        state: distinct(issues.map((issue) => issue.state)),
        priority: distinct(jiraIssues.map((issue) => issue.priority ?? NO_PRIORITY))
            .sort((lhs, rhs) => priorityIndex(lhs) - priorityIndex(rhs) || 0),
        project: distinct(jiraIssues.map((issue) => issue.project)),
    });

    const availableLabels = $derived.by(() => {
        const labels = new Map<string, { label: Label; color: string }>();
        for (const issue of issues) {
            for (const label of issue.labels ?? []) {
                if (labels.has(label.name)) continue;
                labels.set(label.name, { label, color: issue.subtype === "github" ? `#${label.color}` : label2color(label) });
            }
        }
        return [...labels.values()].sort((lhs, rhs) => lhs.label.name.localeCompare(rhs.label.name));
    });


    const SORT_ORDERS = {
        name: {
            field: "title",
            friendlyString: "By title",
            f: (lhs: Issue, rhs: Issue) => reverseSort ? getTitle(rhs).localeCompare(getTitle(lhs)) : getTitle(lhs).localeCompare(getTitle(rhs))
        },
        repo: {
            field: "repo",
            friendlyString: "By repository",
            f: (lhs: Issue, rhs: Issue) => reverseSort ? getRepo(rhs).localeCompare(getRepo(lhs)) : getRepo(lhs).localeCompare(getRepo(rhs))
        },
        date: {
            field: "added_on",
            friendlyString: "By date",
            f: (lhs: Issue, rhs: Issue) => reverseSort ? Date.parse(rhs.added_on) - Date.parse(lhs.added_on) : Date.parse(lhs.added_on) - Date.parse(rhs.added_on)
        },
        priority: {
            field: "priority",
            friendlyString: "By priority",
            f: (lhs: Issue, rhs: Issue) => {
                const lhsRank = priorityRank(lhs);
                const rhsRank = priorityRank(rhs);
                if (lhsRank === rhsRank) return Date.parse(rhs.added_on) - Date.parse(lhs.added_on);
                if (lhsRank === Infinity) return 1;
                if (rhsRank === Infinity) return -1;
                return reverseSort ? lhsRank - rhsRank : rhsRank - lhsRank;
            }
        }
    };

    const labelActive = function(name: string, selectedLabels: Label[]) {
        return selectedLabels.some(l => l.name == name);
    };

    const handleLabelClick = function(label: Label) {
        if (labelActive(label.name, selectedLabels)) {
            selectedLabels = selectedLabels.filter((l: Label) => l.name != label.name);
        } else {
            selectedLabels.push(label);
            selectedLabels = selectedLabels;
        }
        currentPage = 0;
    };

    const toggleFilter = function(group: FilterGroup, value: string, checked: boolean) {
        if (checked) {
            excluded[group].delete(value);
        } else {
            excluded[group].add(value);
        }
        currentPage = 0;
    };

    const submitIssue = async function () {
        try {
            if (!testId) return;
            let apiResponse = await fetch(`/api/v1/test/${testId}/run/${id}/issues/submit`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    issue_url: newIssueUrl,
                }),
            });
            newIssueUrl = "";
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {

                fetchIssues();
            } else {
                throw apiJson;
            }
        } catch (error) {
            if ((error as {status: string, response: { arguments: string[] }})?.status === "error") {
                sendMessage(
                    "error",
                    `API Error while submitting an issue on a test run.\nMessage: ${(error as {status: string, response: { arguments: string[] }}).response.arguments[0]}`,
                    "GithubIssueContainer::submit"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during issue submission.",
                    "GithubIssueContainer::submit"
                );
            }
        }
    };

    const shouldFilter = function (issue: Issue, filterString: string) {
        if (isExcluded(issue)) return true;
        if (shouldFilterByLabels(issue, selectedLabels)) return true;
        if (!filterString) return false;
        if (!issue) return true;
        let allTerms = "";
        if (issue.subtype == "github") {
            let i = issue as GithubSubtype;
            allTerms = `${i.owner}$$${i.title}$$${i.repo}#${i.number}`;
        } else {
            let i = issue as JiraSubtype;
            allTerms = `${i.project}$$${i.summary}#${i.key}`;
        }

        return allTerms.toLowerCase().search(filterString.toLowerCase()) == -1;
    };

    const isExcluded = function(issue: Issue) {
        if (excluded.state.has(issue.state)) return true;
        if (issue.subtype !== "jira") return false;
        const jira = issue as JiraSubtype;
        return excluded.priority.has(jira.priority ?? NO_PRIORITY) || excluded.project.has(jira.project);
    };

    const shouldFilterByLabels = function(issue: Issue, selectedLabels: Label[]) {
        if (selectedLabels.length == 0) return false;
        return !(issue.labels ?? []).some(label => labelActive(label.name, selectedLabels));
    };

    const paginateIssues = function(issues: Issue[], sortCriteria: SortCriteria = "name", reverse = false, filterString = "") {
        if (issues.length == 0) return [];
        const sorted = Array.from(issues).sort(SORT_ORDERS[sortCriteria].f);
        const filtered = sorted.filter(v => !shouldFilter(v, filterString));
        const steps = Math.max(parseInt(String(filtered.length / PAGE_SIZE)) + 1, 1);
        const pages = Array
            .from({length: steps}, () => [])
            .map((_, pageIdx) => {
                const sliceIdx = pageIdx * PAGE_SIZE;
                const slice = filtered.slice(sliceIdx, PAGE_SIZE + sliceIdx);
                return [...slice];
            });
        return pages;
    };

    let sortedIssues = $derived(paginateIssues(issues, sortCriteria, reverseSort, filterString));

    $effect(() => {
        // Read both props together as a single dependency so the effect fires
        // exactly once even when both change in the same Svelte flush.
        void [productVersion, includeNoVersion];
        untrack(() => fetchIssues());
    });
</script>

{#snippet filterGroup(title: string, group: FilterGroup, values: string[])}
    <div class="d-flex flex-wrap align-items-center mb-1" role="group" aria-label={title}>
        <span class="me-2 small text-muted">{title}</span>
        {#each values as value, idx (value)}
            <div class="form-check form-check-inline mb-0">
                <input
                    class="form-check-input"
                    type="checkbox"
                    id="{uid}-{group}-{idx}"
                    checked={!excluded[group].has(value)}
                    onchange={(e) => toggleFilter(group, value, e.currentTarget.checked)}
                />
                <label class="form-check-label" for="{uid}-{group}-{idx}">{optionLabel(value)}</label>
            </div>
        {/each}
    </div>
{/snippet}

<div>
    {#if !submitDisabled}
        <div class="container-fluid mb-2">
            <div class="row">
                <div class="col-6">
                    <div class="dropdown mb-2">
                        <button
                            class="btn btn-success dropdown-toggle"
                            type="button"
                            data-bs-toggle="dropdown"
                        >
                            New Issue
                        </button>
                        <ul class="dropdown-menu">
                            <li>
                                <h6 class="dropdown-header">Jira Projects</h6>
                            </li>
                                <li>
                                    <a
                                        target="_blank"
                                        class="dropdown-item"
                                        href="https://scylladb.atlassian.net/secure/CreateIssue.jspa?pid=10782"
                                        >Argus</a
                                    >
                                </li>
                            {#each newIssueDestinations[pluginName] ??  newIssueDestinations[PLUGIN_NAMES.SCT] as destination}
                                <li>
                                    <a
                                        target="_blank"
                                        class="dropdown-item"
                                        href="{destination.url}"
                                        >{destination.name}</a
                                    >
                                </li>
                            {/each}
                        </ul>
                    </div>
                    <div class="input-group flex-nowrap">
                        <input
                            class="form-control"
                            placeholder="Issue URL"
                            type="text"
                            bind:value={newIssueUrl}
                        />
                        <input
                            class="btn btn-success"
                            type="button"
                            value="Add"
                            onclick={submitIssue}
                        />
                    </div>
                </div>
            </div>
        </div>
    {/if}
    <div class="container-fluid mb-2">
        {#if issues.length > 0}
            <h6 class="d-flex">
                <div class="ms-auto">
                    <IssuesCopyModal sortedIssues={sortedIssues} currentPage={currentPage} selectedLabels={selectedLabels}>
                        <Fa icon={faCopy}/>
                    </IssuesCopyModal>
                </div>
            </h6>
            <div class="row">
                <div class="col">
                    <input class="form-control form-input" type="text" placeholder="Filter issues..." bind:value={filterString}>
                    <div class="mb-2">Options</div>
                    <div class="d-flex align-items-center mb-2">
                        <div class="ms-2 form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="sortCheckOrder" bind:checked={reverseSort}>
                            <label class="form-check-label" for="sortCheckOrder">
                                Descending order
                            </label>
                        </div>
                    </div>
                    {@render filterGroup("Status", "state", filterOptions.state)}
                    {#if jiraIssues.length > 0}
                        {@render filterGroup("Priority", "priority", filterOptions.priority)}
                        {@render filterGroup("Space", "project", filterOptions.project)}
                    {/if}
                </div>
                <div class="col">
                    <select class="form-select" aria-label="Sort issues" bind:value={sortCriteria}>
                        {#each Object.entries(SORT_ORDERS) as [sortName, meta]}
                            <option value="{sortName}">{meta.friendlyString}</option>
                        {/each}
                    </select>
                    <div class="mb-2">Issues per page</div>
                    <select class="form-select mb-2" placeholder="Issues per page" onchange={(e) => PAGE_SIZE = parseInt((e.target as HTMLOptionElement)?.value)} value=10>
                        <option value="10">10</option>
                        <option value="25">25</option>
                        <option value="50">50</option>
                        <option value="100">100</option>
                    </select>
                </div>
            </div>
            {#if availableLabels.length > 0}
                <div class="row">
                    <div class="rounded border p-2 bg-light-one">
                        <div role="button" tabindex="0" class="mb-1 w-100" onkeypress={() => (showAllLabels = !showAllLabels)} onclick={() => (showAllLabels = !showAllLabels)}>All Labels <Fa icon={showAllLabels ? faChevronUp : faChevronDown}/></div>
                        <div class="collapse" class:show={showAllLabels}>
                            <div class="d-flex p-2 bg-dark rounded shadow-sm flex-wrap" role="group" aria-label="All labels">
                                {#each availableLabels as { label, color } (label.name)}
                                    {@const active = labelActive(label.name, selectedLabels)}
                                    <button
                                        class="btn btn-sm m-1 border {active ? 'border-2 border-light' : 'border-dark'}"
                                        style="background-color: {color}; color: {labelTextColor(color)};"
                                        aria-pressed={active}
                                        onclick={() => handleLabelClick(label)}
                                    >
                                        {#if active}<Fa icon={faCheck} />{/if}
                                        {label.name}
                                    </button>
                                {/each}
                            </div>
                        </div>
                    </div>
                </div>
            {/if}
            <div class="row">
                {#each sortedIssues[currentPage] ?? [] as issue, idx (issue.id)}
                    <IssueCard {runId} issue={sortedIssues[currentPage][idx]} aggregated={aggregateByIssue} deleteEnabled={!submitDisabled} on:submitToCurrent on:issueDeleted={fetchIssues} on:labelClick={(e: any) => handleLabelClick(e.detail)}/>
                {/each}
            </div>
            <div class="d-flex ">
                {#each sortedIssues as page, pageIdx}
                    {#if page.length > 0}
                        <div class="ms-1 p-1">
                            <button class="btn btn-sm btn-primary" onclick={() => currentPage = pageIdx}>{pageIdx + 1}</button>
                        </div>
                    {/if}
                {/each}
            </div>
        {:else}
            <div class="row">
                <div class="col text-center text-muted p-3">
                    {#if fetching}
                        <span class="spinner-border spinner-border-sm"></span> Fetching...
                    {:else if productVersion}
                        No issues linked for version {productVersion === "!noVersion" ? "runs without a version" : productVersion}.
                    {:else}
                        No issues found.
                    {/if}
                </div>
            </div>
        {/if}
    </div>
</div>

<style>
</style>
