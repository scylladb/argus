<script lang="ts">
    import Issues from "../../Github/Issues.svelte";
    let {
        dashboardObject,
        dashboardObjectType,
        stats,
        settings,
        productVersion,
        clickedTests
    } = $props();


    let issuesClicked = $state(false);
</script>

<div class="accordion">
    <div class="accordion-item">
        <h2 class="accordion-header">
            <button
                class="accordion-button collapsed"
                type="button"
                data-bs-toggle="collapse"
                data-bs-target="#collapseIssues"
                onclick={() => issuesClicked = true}
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
                    <Issues
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
