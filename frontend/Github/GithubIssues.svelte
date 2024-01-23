<script>
    import { onMount } from "svelte";
    import { PLUGIN_NAMES } from "../Common/PluginNames";
    import { newIssueDestinations } from "../Common/IssueDestinations";
    import GithubIssue from "./GithubIssue.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { faCopy } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    export let id = "";
    export let testId;
    export let pluginName;
    export let filter_key = "run_id";
    export let submitDisabled = false;
    export let aggregateByIssue = false;
    let newIssueUrl = "";
    let issues = [];
    let fetching = false;
    const fetchIssues = async function () {
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
/*
    id = columns.UUID(primary_key=True, default=uuid4, partition_key=True)
    added_on = columns.DateTime(default=datetime.utcnow)
    release_id = columns.UUID(index=True)
    group_id = columns.UUID(index=True)
    test_id = columns.UUID(index=True)
    run_id = columns.UUID(index=True)
    user_id = columns.UUID(index=True)
    type = columns.Text()
    owner = columns.Text()
    repo = columns.Text()
    issue_number = columns.Integer()
    last_status = columns.Text()
    title = columns.Text()
    url = columns.Text()
*/

    let sortCriteria = "date";
    let reverseSort = true;
    let currentPage = 0;
    let filterString = "";

    const SORT_ORDERS = {
        name: {
            field: "title",
            friendlyString: "By title",
            f: (lhs, rhs) => reverseSort ? rhs.title.localeCompare(lhs.title.localeCompare) : lhs.title.localeCompare(lhs.title.localeCompare)
        },
        repo: {
            field: "repo",
            friendlyString: "By repository",
            f: (lhs, rhs) => reverseSort ? rhs.repo.localeCompare(lhs.repo.localeCompare) : lhs.repo.localeCompare(lhs.repo.localeCompare)
        },
        date: {
            field: "added_on",
            friendlyString: "By date",
            f: (lhs, rhs) => reverseSort ? new Date(rhs.added_on) - new Date(lhs.added_on) : new Date(lhs.added_on) - new Date(rhs.added_on)
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
                    `API Error while submitting an issue on a test run.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during issue submission."
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
        if (!filterString) return false;
        if (!issue) return true;
        const allTerms = `${issue.owner}$$${issue.title}$$${issue.repo}#${issue.issue_number}`;
        return allTerms.toLowerCase().search(filterString) == -1;
    };

    /**
     * 
     * @param {{title: string, added_on: string, repo: string}[]} issues
     * @param sortCriteria
     * @param reverse
     */
    const paginateIssues = function(issues, sortCriteria = "default", reverse = false, filterString = "") {
        console.log("Issues: ", issues);
        if (issues.length == 0) return [];
        const sorted = Array.from(issues).sort(SORT_ORDERS[sortCriteria].f);
        console.log("Sorted: ", sorted);
        const filtered = sorted.filter(v => !shouldFilter(v, filterString));
        console.log("Filtered: ", filtered);
        const PAGE_SIZE = 10;
        const steps = Math.max(parseInt(filtered.length / PAGE_SIZE) + 1, 1);
        const pages = Array
            .from({length: steps}, () => [])
            .map((_, pageIdx) => {
                const sliceIdx = pageIdx * PAGE_SIZE;
                const slice = filtered.slice(sliceIdx, PAGE_SIZE + sliceIdx);
                return [...slice];
            });
        console.log("Final: ", pages);
        return pages;
    };

    let sortedIssues = paginateIssues(issues, sortCriteria, reverseSort);
    $: sortedIssues = paginateIssues(issues, sortCriteria, reverseSort, filterString);


    const exportIssueAsFormattedList = function(issues) {
        let issueFormattedList = issues
            .sort((a, b) => a.issue_number - b.issue_number)
            .map(val => ` * ${val.owner}/${val.repo}#${val.issue_number}: ${val.title} - ${val.url}`);
        navigator.clipboard.writeText(`Current Issues\n${issueFormattedList.join("\n")}`);
    };

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
                            on:click={submitIssue}
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
                <div class="ms-auto"><button class="btn btn-success" on:click={() => exportIssueAsFormattedList(sortedIssues[currentPage] ?? [])}><Fa icon={faCopy}/></button></div>
            </h6>
            <div class="row">
                <div class="col">
                    <input class="form-control form-input" type="text" placeholder="Filter issues..." bind:value={filterString}>
                </div>
                <div class="col">
                    <select class="form-select" bind:value={sortCriteria}>
                        {#each Object.entries(SORT_ORDERS) as [sortName, meta]}
                            <option value="{sortName}">{meta.friendlyString}</option>
                        {/each}
                    </select>
                    <div>
                        <input class="form-check-input" type="checkbox" id="sortCheckOrder" bind:checked={reverseSort}>
                        <label class="form-check-label" for="sortCheckOrder">
                            Descending order
                        </label>
                    </div>
                </div>
            </div>
            <div class="row">
                {#each sortedIssues[currentPage] ?? [] as issue (issue.id)}
                    <GithubIssue {issue} aggregated={aggregateByIssue} deleteEnabled={!submitDisabled} on:issueDeleted={fetchIssues} />
                {/each}
            </div>
            <div class="d-flex ">
                {#each sortedIssues as page, pageIdx}
                    {#if page.length > 0}
                        <div class="ms-1 p-1">
                            <button class="btn btn-sm btn-primary" on:click={() => currentPage = pageIdx}>{pageIdx + 1}</button>
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
