<script lang="ts" type="ts">
    import Fa from "svelte-fa";
    import {onMount} from "svelte";
    import GithubIssue from "../../../Github/GithubIssue.svelte";
    import {faBug} from "@fortawesome/free-solid-svg-icons";
    import GithubIssuesCopyModal from "../../../Github/GithubIssuesCopyModal.svelte";

    let { runId, runStatus } = $props();
    let issues = $state([]);
    let fetching = $state(true);
    let paginatedIssues = $derived([issues]);


    const fetchIssues = async function () {
        issues = [];
        fetching = true;
        try {
            let params = new URLSearchParams({
                filterKey: "run_id",
                id: runId,
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
    onMount(async () => {
        if (runStatus === "failed") {
            await fetchIssues();
        }
    });

</script>
{#if runStatus === "failed"}
    {#if fetching}
        <div class="text-center">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
        </div>
    {:else}
        {#if issues.length > 0}
            <GithubIssuesCopyModal sortedIssues={paginatedIssues} btnClass="btn-danger">
                {issues.length}
                <Fa icon={faBug}/>
            </GithubIssuesCopyModal>
        {/if}
    {/if}
{/if}
