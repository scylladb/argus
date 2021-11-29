<script>
    import { onMount } from "svelte";
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
    <div class="container">
        <div class="row justify-content-center mb-2">
            <div class="col-6">
                <div class="input-group flex-nowrap">
                    <span class="input-group-text" id="addon-wrapping">New</span>
                    <input class="form-control" placeholder="Github Issue URL" type="text" bind:value={newIssueUrl} />
                    <input class="btn btn-success" type="button" value="Add" on:click={submitIssue} />
                </div>
            </div>
        </div>
    </div>
    {/if}
    <div class="container-fluid">
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
