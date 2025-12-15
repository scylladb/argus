<script module lang="ts">
    export type GithubState = "open" | "closed";
    export type JiraState = "in review" | "blocked" | "todo" | "in progress" | "ready for merge" | "done" | "duplicate" | "won't fix" | "new";
    export type State = GithubState | JiraState;
    export interface Label {
        id: string,
        name: string,
        color: string,
        description: string,
    }

    export interface Link {
        id: string,
        test_id: string,
        run_id: string,
        release_id: string,
        type: string,
        added_on: string,
        user_id: string,
    }

    export interface Issue {
        subtype: "github" | "jira",
        id: string,
        state: State,
        added_on: string,
        labels: Label[],
        user_id: string,
        links: Link[],
    }

    export interface GithubSubtype extends Issue {
        repo: string,
        owner: string,
        number: string,
        title: string,
        state: GithubState,
        url: string,
        assignees: { html_url: string, login: string }[]
    }

    export type StateFilter = Record<State, boolean>;

    export interface JiraSubtype extends Issue {
        key: string,
        summary: string,
        project: string,
        permalink: string,
        state: JiraState,
        assignees: string[],
    }

    export interface TestRun {
        build_id: string,
        build_number: string,
        build_job_url: string,
        assignee: string,
        group_id: string,
        release_id: string,
        test_id: string,
        id: string,
    }

    export interface RichAssignee {
        login: string,
        html_url: string,
    }


    export const getTitle = function(i: Issue): string {
        if (i.subtype == "github") {
            return (i as GithubSubtype).title;
        } else {
            return (i as JiraSubtype).summary;
        }
    };

    export const getRepo = function(i: Issue): string {
        if (i.subtype == "github") {
            return (i as GithubSubtype).repo;
        } else {
            return (i as JiraSubtype).project;
        }
    };

    export const getNumber = function(i: Issue): number {
        if (i.subtype == "github") {
            return parseInt((i as GithubSubtype).number);
        } else {
            return parseInt((i as JiraSubtype).key.split("-")[1]);
        }
    };

    export const getUrl = function(i: Issue): string {
        if (i.subtype == "github") {
            return (i as GithubSubtype).url;
        } else {
            return (i as JiraSubtype).permalink;
        }
    };

    export const getAssignees = function(i: Issue): string[] {
        if (i.subtype == "github") {
            return (i as GithubSubtype).assignees.map((v) => v.login);
        } else {
            return (i as JiraSubtype).assignees;
        }
    };

    export const getKey = function(i: Issue): string {
        if (i.subtype == "github") {
            let iss = i as GithubSubtype;
            return `${iss.owner}/${iss.repo}#${iss.number}`;
        } else {
            let iss = i as JiraSubtype;
            return `${iss.key}`;
        }
    };

    export const getAssigneesRich = function(i: Issue): RichAssignee[] {
        if (i.subtype == "github") {
            return (i as GithubSubtype).assignees;
        } else {
            return (i as JiraSubtype).assignees.map(v => ({ login: v, html_url: "#" }));
        }
    };


    export const label2color = function (label: Label): string {
        const START_COLOR = [255, 238, 0];
        const END_COLOR = [0, 32, 255];
        const factor = (parseInt(sha1(label.name).slice(0,16), 16) % 10000) / 10000;

        const lerp = (c1: number, c2: number, frac: number) => Math.round(((c2 - c1) * frac + c1)) & 0xff;
        let color = START_COLOR.map((c1, idx) => lerp(c1, END_COLOR[idx], factor)).join(", ");
        return `rgb(${color})`;
    }

</script>

<script lang="ts">
    import { onMount } from "svelte";
    import { PLUGIN_NAMES } from "../Common/PluginNames";
    import { newIssueDestinations } from "../Common/IssueDestinations";
    import GithubIssue from "./GithubIssue.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { faChevronDown, faChevronUp, faCopy } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import Color from "color";
    import IssuesCopyModal from "./IssuesCopyModal.svelte";
    import queryString from 'query-string';
    import JiraIssue from "../Jira/JiraIssue.svelte";
    import { sha1 } from "js-sha1";
    interface Props {
        id?: string;
        runId: any;
        testId: any;
        pluginName: any;
        filter_key?: string;
        submitDisabled?: boolean;
        aggregateByIssue?: boolean;
    }

    let {
        id = "",
        runId,
        testId,
        pluginName,
        filter_key = "run_id",
        submitDisabled = false,
        aggregateByIssue = false
    }: Props = $props();
    let newIssueUrl = $state("");
    let issues: Issue[] = $state([]);
    let fetching = $state(false);
    let showAllLabels = $state(false);
    export const fetchIssues = async function () {
        issues = [];
        fetching = true;
        try {

            let params = queryString.stringify({
                filterKey: filter_key,
                id: id,
                aggregateByIssue: new Number(aggregateByIssue),
            }).toString();
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

    let sortCriteria: "name" | "repo" | "date" = $state("date");
    let reverseSort = $state(true);
    let currentPage = $state(0);
    let PAGE_SIZE = $state(10);
    let filterString = $state("");
    let availableLabels: Label[] = [];
    let selectedLabels: Label[] = $state([]);
    const stateFilter: Record<State, boolean> = $state({
        open: true,
        closed: true,
        "in progress": true,
        "in review": true,
        "ready for merge": true,
        "blocked": true,
        "done": true,
        "duplicate": true,
        "won't fix": true,
        todo: true,
        new: true,
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
        }
    };

    /**
     *
     * @param {number} id
     * @param {Object[]} selectedLabels
     */
    const labelActive = function(id: string, selectedLabels: Label[]) {
        return !!selectedLabels.find(l => l.id == id);
    };

    const handleLabelClick = function(label: Label) {
        if (labelActive(label.id, selectedLabels)) {
            selectedLabels = selectedLabels.filter((l: Label) => l.id != label.id);
        } else {
            selectedLabels.push(label);
            selectedLabels = selectedLabels;
        }
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
        if (shouldFilterByState(issue, selectedLabels, stateFilter)) return true;
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

    const shouldFilterByState = function(issue: Issue, selectedLabels: Label[], stateFilter: StateFilter) {
        if (!stateFilter[issue.state]) return true;
        if (selectedLabels.length == 0) return false;
        return !issue.labels.map(label => !!selectedLabels.find(selectedLabel => label.id == selectedLabel.id)).includes(true);
    };

    const paginateIssues = function(issues: Issue[], sortCriteria: "name" | "repo" | "date" = "name", reverse = false, filterString = "") {
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

    onMount(() => {
        fetchIssues();
    });
</script>

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
                                <h6 class="dropdown-header">Repositories</h6>
                            </li>
                                <li>
                                    <a
                                        target="_blank"
                                        class="dropdown-item"
                                        href="https://github.com/scylladb/argus/issues/new/choose"
                                        >Argus</a
                                    >
                                </li>
                            {#each newIssueDestinations[pluginName] ??  newIssueDestinations[PLUGIN_NAMES.SCT] as destination}
                                <li>
                                    <a
                                        target="_blank"
                                        class="dropdown-item"
                                        href="{destination.url}/issues/new/choose"
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
                <div>Issues</div>
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
                            <input class="form-check-input" type="checkbox" id="issueOpenCheckbox" bind:checked={stateFilter.open}>
                            <label class="form-check-label" for="issueOpenCheckbox">
                                Open
                            </label>
                        </div>
                        <div class="ms-2 form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="issueClosedCheckbox" bind:checked={stateFilter.closed}>
                            <label class="form-check-label" for="issueClosedCheckbox">
                                Closed
                            </label>
                        </div>
                        <div class="ms-2 form-check form-switch">
                            <input class="form-check-input" type="checkbox" id="sortCheckOrder" bind:checked={reverseSort}>
                            <label class="form-check-label" for="sortCheckOrder">
                                Descending order
                            </label>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <select class="form-select" bind:value={sortCriteria}>
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
            <div class="row">
                <div class="rounded border p-2 bg-light-one">
                    <div role="button" tabindex="0" class="mb-1 w-100" onkeypress={() => (showAllLabels = !showAllLabels)} onclick={() => (showAllLabels = !showAllLabels)}>All Labels <Fa icon={showAllLabels ? faChevronUp : faChevronDown}/></div>
                    <div class="collapse" class:show={showAllLabels}>
                        <div class="d-flex p-2 bg-dark rounded shadow-sm flex-wrap">
                            {#each availableLabels as label}
                                <button
                                    class="ms-2 btn btn-sm btn-secondary m-1"
                                    style="border-color: #{label.color}; color: #{label.color}; background-color: {labelActive(label.id, selectedLabels) ? Color(`#${label.color}`).darken(0.75) : "rgba(1,1,1,0)"}"
                                    onclick={() => handleLabelClick(label)}
                                >
                                    {label.name}
                                </button>
                            {/each}
                        </div>
                    </div>
                </div>
            </div>
            <div class="row">
                {#each sortedIssues[currentPage] ?? [] as issue, idx (issue.id)}
                    {#if issue.subtype == "github"}
                        <GithubIssue {runId} bind:issue={sortedIssues[currentPage][idx] as GithubSubtype} aggregated={aggregateByIssue} deleteEnabled={!submitDisabled} on:submitToCurrent on:issueDeleted={fetchIssues} on:labelClick={(e) => handleLabelClick(e.detail)}/>
                    {:else if issue.subtype == "jira"}
                        <JiraIssue {runId} bind:issue={sortedIssues[currentPage][idx] as JiraSubtype} aggregated={aggregateByIssue} deleteEnabled={!submitDisabled} on:submitToCurrent on:issueDeleted={fetchIssues} on:labelClick={(e) => handleLabelClick(e.detail)}/>
                    {/if}
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
                <div class="col text-center text-muted">
                    {#if fetching}
                        <span class="spinner-border spinner-border-sm"></span> Fetching...
                    {:else}
                        No Issues.
                    {/if}
                </div>
            </div>
        {/if}
    </div>
</div>

<style>
</style>
