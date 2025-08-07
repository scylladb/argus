<script lang="ts">
    import { run } from 'svelte/legacy';

    import { onMount } from "svelte";
    import { PLUGIN_NAMES } from "../Common/PluginNames";
    import { newIssueDestinations } from "../Common/IssueDestinations";
    import GithubIssue from "./GithubIssue.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { faChevronDown, faChevronUp, faCopy } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    import Color from "color";
    import GithubIssuesCopyModal from "./GithubIssuesCopyModal.svelte";
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
    let issues = $state([]);
    let fetching = $state(false);
    let showAllLabels = $state(false);
    export const fetchIssues = async function () {
        issues = [];
        fetching = true;
        try {
            let params = new URLSearchParams({
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

    let sortCriteria = $state("date");
    let reverseSort = $state(true);
    let currentPage = $state(0);
    let PAGE_SIZE = $state(10);
    let filterString = $state("");
    let availableLabels = [];
    let selectedLabels = $state([]);
    const stateFilter = $state({
        open: true,
        closed: true,
    });

    const SORT_ORDERS = {
        name: {
            field: "title",
            friendlyString: "By title",
            f: (lhs, rhs) => reverseSort ? rhs.title.localeCompare(lhs.title) : lhs.title.localeCompare(rhs.title)
        },
        repo: {
            field: "repo",
            friendlyString: "By repository",
            f: (lhs, rhs) => reverseSort ? rhs.repo.localeCompare(lhs.repo) : lhs.repo.localeCompare(rhs.repo)
        },
        date: {
            field: "added_on",
            friendlyString: "By date",
            f: (lhs, rhs) => reverseSort ? new Date(rhs.added_on) - new Date(lhs.added_on) : new Date(lhs.added_on) - new Date(rhs.added_on)
        }
    };

    /**
     *
     * @param {number} id
     * @param {Object[]} selectedLabels
     */
    const labelActive = function(id, selectedLabels) {
        return !!selectedLabels.find(l => l.id == id);
    };

    const handleLabelClick = function(label) {
        if (labelActive(label.id, selectedLabels)) {
            selectedLabels = selectedLabels.filter(l => l.id != label.id);
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
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error while submitting an issue on a test run.\nMessage: ${error.response.arguments[0]}`,
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

    /**
     *
     * @param {{title: string, added_on: string, repo: string}} issue
     * @param {string} filterString
     */
    const shouldFilter = function (issue, filterString) {
        if (shouldFilterByState(issue, selectedLabels, stateFilter)) return true;
        if (!filterString) return false;
        if (!issue) return true;
        const allTerms = `${issue.owner}$$${issue.title}$$${issue.repo}#${issue.number}`;
        return allTerms.toLowerCase().search(filterString.toLowerCase()) == -1;
    };

    /**
     *
     * @param {{ state: { state: ('open'|'closed'), labels: {id: number, name: string }[]}}}issue
     * @param {{id: number, name: string }[]} selectedLabels
     * @param {{ open: boolean, closed: boolean }} stateFilter
     */
    const shouldFilterByState = function(issue, selectedLabels, stateFilter) {
        if (!stateFilter[issue.state]) return true;
        if (selectedLabels.length == 0) return false;
        return !issue.labels.map(label => !!selectedLabels.find(selectedLabel => label.id == selectedLabel.id)).includes(true);
    };

    /**
     *
     * @param {{title: string, added_on: string, repo: string}[]} issues
     * @param sortCriteria
     * @param reverse
     */
    const paginateIssues = function(issues, sortCriteria = "default", reverse = false, filterString = "") {
        if (issues.length == 0) return [];
        const sorted = Array.from(issues).sort(SORT_ORDERS[sortCriteria].f);
        const filtered = sorted.filter(v => !shouldFilter(v, filterString));
        const steps = Math.max(parseInt(filtered.length / PAGE_SIZE) + 1, 1);
        const pages = Array
            .from({length: steps}, () => [])
            .map((_, pageIdx) => {
                const sliceIdx = pageIdx * PAGE_SIZE;
                const slice = filtered.slice(sliceIdx, PAGE_SIZE + sliceIdx);
                return [...slice];
            });
        return pages;
    };

    let sortedIssues = $state(paginateIssues(issues, sortCriteria, reverseSort));
    run(() => {
        sortedIssues = paginateIssues(issues, sortCriteria, reverseSort, filterString, selectedLabels, stateFilter, PAGE_SIZE);
    });



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
                            placeholder="Github Issue URL"
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
                    <GithubIssuesCopyModal sortedIssues={sortedIssues} currentPage={currentPage} selectedLabels={selectedLabels}>
                        <Fa icon={faCopy}/>
                    </GithubIssuesCopyModal>
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
                    <select class="form-select mb-2" placeholder="Issues per page" onchange={(e) => PAGE_SIZE = parseInt(e.target.value)} value=10>
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
                    <GithubIssue {runId} bind:issue={sortedIssues[currentPage][idx]} aggregated={aggregateByIssue} deleteEnabled={!submitDisabled} on:submitToCurrent on:issueDeleted={fetchIssues} on:labelClick={(e) => handleLabelClick(e.detail)}/>
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
