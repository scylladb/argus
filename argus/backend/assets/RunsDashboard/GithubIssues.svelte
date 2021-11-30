<script>
    import { onMount } from "svelte";
    import { newIssueDestinations } from "./IssueDestinations";
    import GithubIssue from "./GithubIssue.svelte";
    export let id = "";
    export let filter_key = "run_id";
    export let submitDisabled = false;
    let newIssueUrl = "";
    let issues = {};
    const fetchIssues = async function () {
        try {
            let apiResponse = await fetch("/api/v1/issues/get", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    filter_key: filter_key,
                    id: id,
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                issues = apiJson.response;
                console.log(issues);
            } else {
                throw apiJson;
            }
        } catch (error) {
            console.log(error);
        }
    };

    const submitIssue = async function () {
        try {
            let apiResponse = await fetch("/api/v1/issues/submit", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    issue_url: newIssueUrl,
                    run_id: id,
                }),
            });
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                fetchIssues();
            } else {
                throw apiJson;
            }
        } catch (error) {
            console.log(error);
        }
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
                        <ul
                            class="dropdown-menu"
                        >
                            <li><h6 class="dropdown-header">Repositories</h6></li>
                            {#each newIssueDestinations as destination}
                            <li>
                                <a target="_blank" class="dropdown-item" href="{destination.url}/issues/new/choose">{destination.name}</a>
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
            <h6>Issues</h6>
        {/if}
        {#each issues as issue}
            <GithubIssue {issue} />
        {:else}
            <div class="row">
                <div class="col text-center text-muted">No Issues.</div>
            </div>
        {/each}
    </div>
</div>

<style>
</style>
