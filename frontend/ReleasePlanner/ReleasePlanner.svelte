<script lang="ts">
    import { run } from 'svelte/legacy';

    import ModalWindow from "../Common/ModalWindow.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { userList } from "../Stores/UserlistSubscriber";
    import ReleasePlanCreator from "./ReleasePlanCreator.svelte";
    import ReleasePlanCopyForm from "./ReleasePlanCopyForm.svelte";
    import ReleasePlan from "./ReleasePlan.svelte";


    let { release, plans = $bindable() } = $props();

    let users = $state({});

    run(() => {
        users = $userList;
    });

    let creatingPlan = $state(false);
    let deletingPlan = $state(false);
    let editingPlan = $state(false);
    let copyingPlan = $state(false);
    let createFromPlan = $state(false);
    let deleteViewForPlan = $state(true);
    let selectedPlan = $state();
    let releaseRedirect = $state("");

    let expandedPlans = $state({});

    const sortPlans = function(lhs, rhs) {
        if (!lhs.target_version && !rhs.target_version) return 0;
        if (!lhs.target_version && rhs.target_version) return -1;
        if (lhs.target_version && !rhs.target_version) return 1;
        if (lhs.target_version < rhs.target_version) return -1;
        if (lhs.target_version == rhs.target_version) return 0;
        if (lhs.target_version > rhs.target_version) return 1;
        return 0;
    };

    const fetchAllPlans = async function () {
        try {
            const response = await fetch(`/api/v1/planning/release/${release.id}/all`);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            plans = json.response;

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching release plans.\nMessage: ${error.response.arguments[0]}`,
                    "ReleasePlanner::fetchAllPlans"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during release plan fetch",
                    "ReleasePlanner::fetchAllPlans"
                );
                console.log(error);
            }
        }
    };

    const handlePlanCopy = async function (e) {
        try {
            let payload = e.detail;
            const response = await fetch("/api/v1/planning/plan/copy", {
                headers: {
                    "Content-Type": "application/json",
                },
                method: "POST",
                body: JSON.stringify(payload),
            });

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            selectedPlan = undefined;
            copyingPlan = false;
            await fetchAllPlans();
            releaseRedirect = payload.targetReleaseId != release.id ? payload.targetReleaseName : "";

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when copying a plan.\nMessage: ${error.response.arguments[0]}`,
                    "ReleasePlanner::copy"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during plan copy",
                    "ReleasePlanner::copy"
                );
                console.log(error);
            }
        } finally {
            // empty
        }
    };

    const handlePlanDelete = async function () {

        try {
            const response = await fetch(`/api/v1/planning/plan/${selectedPlan.id}/delete?deleteView=${new Number(deleteViewForPlan)}`, {
                method: "DELETE",
            });

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            selectedPlan = undefined;
            deletingPlan = false;
            await fetchAllPlans();

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when deleting a plan.\nMessage: ${error.response.arguments[0]}`,
                    "ReleasePlanner::delete"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during plan deletion",
                    "ReleasePlanner::delete"
                );
                console.log(error);
            }
        } finally {
            // empty
        }
    };

</script>

{#if creatingPlan}
    <ModalWindow on:modalClose={() => (creatingPlan = false)}>
        {#snippet title()}
                <div >
                Creating a release plan
            </div>
            {/snippet}
        {#snippet body()}
                <div >
                <ReleasePlanCreator {release} {plans} on:planCreated={() => {
                    creatingPlan = false;
                    fetchAllPlans();
                }}/>
            </div>
            {/snippet}
    </ModalWindow>
{/if}

{#if createFromPlan}
    <ModalWindow on:modalClose={() => {selectedPlan = undefined; createFromPlan = false;}}>
        {#snippet title()}
                <div >
                Creating <span class="fw-bold">Execution plan</span> from <span class="fw-bold">{selectedPlan.name}</span>
            </div>
            {/snippet}
        {#snippet body()}
                <div >
                <ReleasePlanCreator mode="createFrom" {release} {plans} plan={Object.assign({}, selectedPlan)} on:planCreated={() => {
                    createFromPlan = false;
                    selectedPlan = undefined;
                    fetchAllPlans();
                }}/>
            </div>
            {/snippet}
    </ModalWindow>
{/if}

{#if copyingPlan}
    <ModalWindow on:modalClose={() => { selectedPlan = undefined; copyingPlan = false; }}>
        {#snippet title()}
                <div >
                Copying plan...
            </div>
            {/snippet}
        {#snippet body()}
                <div >
                <ReleasePlanCopyForm {release} plan={selectedPlan} on:copyCanceled={() => { selectedPlan = undefined; copyingPlan = false; }} on:copyConfirmed={handlePlanCopy} />
            </div>
            {/snippet}
    </ModalWindow>
{/if}

{#if releaseRedirect}
    <ModalWindow on:modalClose={() => releaseRedirect = ""}>
        {#snippet title()}
                <div >
                Plan copied!
            </div>
            {/snippet}
        {#snippet body()}
                <div >
                You have copied a plan into another release. <a href="/release/{releaseRedirect}/planner">Click here</a> to go to that release planning page.
            </div>
            {/snippet}
    </ModalWindow>
{/if}

{#if editingPlan}
    <ModalWindow on:modalClose={() => {selectedPlan = undefined; editingPlan = false;}}>
        {#snippet title()}
                <div >
                Editing <span class="fw-bold">{selectedPlan.name}</span>
            </div>
            {/snippet}
        {#snippet body()}
                <div >
                <ReleasePlanCreator mode="edit" {plans} {release} plan={Object.assign({}, selectedPlan)} on:planUpdated={() => {
                    editingPlan = false;
                    selectedPlan = undefined;
                    fetchAllPlans();
                }}/>
            </div>
            {/snippet}
    </ModalWindow>
{/if}

{#if deletingPlan}
    <ModalWindow on:modalClose={() => { selectedPlan = undefined; deletingPlan = false; }}>
        {#snippet title()}
                <div >
                Deleting plan <span class="fw-bold">{selectedPlan.name}</span>
            </div>
            {/snippet}
        {#snippet body()}
                <div >
                <div>Are you sure you want to delete this plan?</div>
                <div class="my-2 fw-bold p-2">
                    <label class="form-check-label" for="planDeleteViewCheckbox">Delete attached view</label>
                    <input class="form-check-input" type="checkbox" id="planDeleteViewCheckbox" bind:checked={deleteViewForPlan}>
                </div>

                <div class="d-flex p-2">
                    <button
                        onclick={handlePlanDelete}
                        class="btn btn-danger w-75"
                    >
                        Confirm
                    </button>
                    <button
                        onclick={() => {
                        deletingPlan = false;
                        selectedPlan = undefined;
                    }}
                        class="ms-1 btn btn-secondary w-25"
                    >
                        Cancel
                    </button>
                </div>
            </div>
            {/snippet}
    </ModalWindow>
{/if}

<div class="bg-white rounded shadow-sm m-2 p-2">
    <h1>{release.name}</h1>
    <div class="mb-2">
        <button class="btn btn-success" onclick={() => (creatingPlan = true)}>New Plan</button>
    </div>
    <div class="p-2 bg-light-three rounded">
        {#each plans.sort(sortPlans) as plan (plan.id)}
            <ReleasePlan
                bind:expandedPlans
                {plan}
                on:createFromClick={(e) => {selectedPlan = e.detail; createFromPlan = true; }}
                on:copyClick={(e) => { selectedPlan = e.detail; copyingPlan = true; }}
                on:deleteClick={(e) => { selectedPlan = e.detail; deletingPlan = true; }}
                on:editClick={(e) => { selectedPlan = e.detail; editingPlan = true; }}
            />
        {:else}
             <div class="text-center text-muted">No plans created for this release.</div>
        {/each}
    </div>
</div>
