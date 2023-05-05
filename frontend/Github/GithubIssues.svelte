<script>
    import { onMount } from "svelte";
    import { newIssueDestinations } from "../Common/IssueDestinations";
    import GithubIssue from "./GithubIssue.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { faCopy } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";
    export let id = "";
    export let testId;
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

    const sortIssuesByDate = function(issues) {
        return issues.sort((a,b) => new Date(b.added_on) - new Date(a.added_on));
    };

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
                            {#each newIssueDestinations as destination}
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
                <div class="ms-auto"><button class="btn btn-success" on:click={() => exportIssueAsFormattedList(issues)}><Fa icon={faCopy}/></button></div>
            </h6>
        {/if}
        {#each sortIssuesByDate(issues) as issue}
            <GithubIssue {issue} aggregated={aggregateByIssue} deleteEnabled={!submitDisabled} on:issueDeleted={fetchIssues} />
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
        {/each}
    </div>
</div>

<style>
</style>
