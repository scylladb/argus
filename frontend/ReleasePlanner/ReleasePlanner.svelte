<script>
    import ModalWindow from "../Common/ModalWindow.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { userList } from "../Stores/UserlistSubscriber";
    import ReleasePlanCreator from "./ReleasePlanCreator.svelte";
    import ReleasePlanCopyForm from "./ReleasePlanCopyForm.svelte";
    import ReleasePlan from "./ReleasePlan.svelte";


    export let release;
    export let plans;

    let users = {};

    $: users = $userList;

    let creatingPlan = false;
    let deletingPlan = false;
    let editingPlan = false;
    let copyingPlan = false;
    let createFromPlan = false;
    let deleteViewForPlan = true;
    let selectedPlan;
    let releaseRedirect = "";

    let expandedPlans = {};

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
        <div slot="title">
            Creating a release plan
        </div>
        <div slot="body">
            <ReleasePlanCreator {release} {plans} on:planCreated={() => {
                creatingPlan = false;
                fetchAllPlans();
            }}/>
        </div>
    </ModalWindow>
{/if}

{#if createFromPlan}
    <ModalWindow on:modalClose={() => {selectedPlan = undefined; createFromPlan = false;}}>
        <div slot="title">
            Creating <span class="fw-bold">Execution plan</span> from <span class="fw-bold">{selectedPlan.name}</span>
        </div>
        <div slot="body">
            <ReleasePlanCreator mode="createFrom" {release} {plans} plan={Object.assign({}, selectedPlan)} on:planCreated={() => {
                createFromPlan = false;
                selectedPlan = undefined;
                fetchAllPlans();
            }}/>
        </div>
    </ModalWindow>
{/if}

{#if copyingPlan}
    <ModalWindow on:modalClose={() => { selectedPlan = undefined; copyingPlan = false; }}>
        <div slot="title">
            Copying plan...
        </div>
        <div slot="body">
            <ReleasePlanCopyForm {release} plan={selectedPlan} on:copyCanceled={() => { selectedPlan = undefined; copyingPlan = false; }} on:copyConfirmed={handlePlanCopy} />
        </div>
    </ModalWindow>
{/if}

{#if releaseRedirect}
    <ModalWindow on:modalClose={() => releaseRedirect = ""}>
        <div slot="title">
            Plan copied!
        </div>
        <div slot="body">
            You have copied a plan into another release. <a href="/release/{releaseRedirect}/planner">Click here</a> to go to that release planning page.
        </div>
    </ModalWindow>
{/if}

{#if editingPlan}
    <ModalWindow on:modalClose={() => {selectedPlan = undefined; editingPlan = false;}}>
        <div slot="title">
            Editing <span class="fw-bold">{selectedPlan.name}</span>
        </div>
        <div slot="body">
            <ReleasePlanCreator mode="edit" {plans} {release} plan={Object.assign({}, selectedPlan)} on:planUpdated={() => {
                editingPlan = false;
                selectedPlan = undefined;
                fetchAllPlans();
            }}/>
        </div>
    </ModalWindow>
{/if}

{#if deletingPlan}
    <ModalWindow on:modalClose={() => { selectedPlan = undefined; deletingPlan = false; }}>
        <div slot="title">
            Deleting plan <span class="fw-bold">{selectedPlan.name}</span>
        </div>
        <div slot="body">
            <div>Are you sure you want to delete this plan?</div>
            <div class="my-2 fw-bold p-2">
                <label class="form-check-label" for="planDeleteViewCheckbox">Delete attached view</label>
                <input class="form-check-input" type="checkbox" id="planDeleteViewCheckbox" bind:checked={deleteViewForPlan}>
            </div>

            <div class="d-flex p-2">
                <button
                    on:click={handlePlanDelete}
                    class="btn btn-danger w-75"
                >
                    Confirm
                </button>
                <button
                    on:click={() => {
                        deletingPlan = false;
                        selectedPlan = undefined;
                    }}
                    class="ms-1 btn btn-secondary w-25"
                >
                    Cancel
                </button>
            </div>
        </div>
    </ModalWindow>
{/if}

<div class="bg-white rounded shadow-sm m-2 p-2">
    <h1>{release.name}</h1>
    <div class="mb-2">
        <button class="btn btn-success" on:click={() => (creatingPlan = true)}>New Plan</button>
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
