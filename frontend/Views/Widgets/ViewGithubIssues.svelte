<script>
    import GithubIssues from "../../Github/GithubIssues.svelte";
    export let dashboardObject;
    export let dashboardObjectType;
    export let stats;
    export let settings;
    export let productVersion;
    export let clickedTests;


    let issuesClicked = false;
</script>

<div class="accordion">
    <div class="accordion-item">
        <h2 class="accordion-header">
            <button
                class="accordion-button collapsed"
                type="button"
                data-bs-toggle="collapse"
                data-bs-target="#collapseIssues"
                on:click={() => issuesClicked = true}
            >
                All Issues
            </button>
        </h2>
        <div
            id="collapseIssues"
            class="accordion-collapse collapse bg-light-one"
        >
            <div class="accordion-body">
                {#if issuesClicked}
                    <GithubIssues
                        id={dashboardObject.id}
                        filter_key="view_id"
                        submitDisabled={settings.submitDisabled}
                        aggregateByIssue={settings.aggregateByIssue}
                    />
                {/if}
            </div>
        </div>
    </div>
</div>
