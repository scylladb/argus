<script lang="ts">
    import { run } from 'svelte/legacy';

    import { createEventDispatcher } from "svelte";
    import { getPicture, getUser } from "../Common/UserUtils";
    import { sendMessage } from "../Stores/AlertStore";
    import Fa from "svelte-fa";
    import { faArrowUp, faChevronDown, faChevronUp, faCopy, faLink, faTrash } from "@fortawesome/free-solid-svg-icons";
    import { faClone } from "@fortawesome/free-regular-svg-icons";
    import ViewDashboard from "../Views/ViewDashboard.svelte";
    import ReleaseStats from "../Stats/ReleaseStats.svelte";
    import { faEdit } from "@fortawesome/free-regular-svg-icons";
    import { userList } from "../Stores/UserlistSubscriber";
    import { GLOBAL_STATS_KEY } from "../Common/ViewTypes";


    let users = $state({});
    interface Props {
        plan: any;
        detached?: boolean;
        expandedPlans: any;
    }

    let { plan, detached = false, expandedPlans = $bindable() }: Props = $props();
    let planStats = $state({});

    let owner = $derived(getUser(plan.owner, users));
    run(() => {
        users = $userList;
    });

    const dispatch = createEventDispatcher();

    const fetchViewForPlan = async function (viewId) {
        try {
            const response = await fetch(`/api/v1/views/get?viewId=${viewId}`);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            let view = json.response;
            view.widget_settings = JSON.parse(view.widget_settings);

            return view;

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching view for release plan.\nMessage: ${error.response.arguments[0]}`,
                    "ReleasePlanner::fetchAllPlans"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during view for plan fetch",
                    "ReleasePlanner::fetchAllPlans"
                );
                console.log(error);
            }
        }
    };

</script>

<div class="rounded p-2 mb-2 bg-white shadow-sm">
    {#if detached}
        <a href="/release/by-id/{plan.release_id}/planner" class="btn btn-sm btn-secondary"><Fa icon={faArrowUp}/> Back to planner</a>
    {/if}
    <div class=" d-flex align-items-center">
        <div class="">
            {plan.name}
            <div class="text-muted text-sm">{plan.description}</div>
            {#if owner}
                <div><img class="img-profile" src="{getPicture(owner.picture_id)}" alt=""> <span class="fw-bold">@{owner.username}</span></div>
            {/if}
        </div>
        <div class="ms-auto text-muted w-10" style="font-size: 3em;">
            {plan.target_version}
            {#if planStats}
                <div>
                    <ReleaseStats releaseStats={planStats[GLOBAL_STATS_KEY]} />
                </div>
            {/if}
        </div>
        {#if !detached}
            <div class="ms-2">
                {#if planStats}
                    <button onclick={() => { expandedPlans[plan.id] = (!expandedPlans[plan.id]); }} class="btn btn-primary"><Fa icon={expandedPlans[plan.id] ? faChevronUp : faChevronDown}/></button>
                {:else}
                    <button class="btn btn-primary"><span class="spinner-grow spinner-grow-sm"></span></button>
                {/if}
            </div>
            {#if !plan.created_from}
                <div class="ms-2">
                    <button class="btn btn-primary" onclick={() => { dispatch("createFromClick", plan); }}><Fa icon={faClone}/></button>
                </div>
            {/if}
            <div class="ms-2">
                <button class="btn btn-warning" onclick={() => { dispatch("editClick", plan); }}><Fa icon={faEdit}/></button>
            </div>
            <div class="ms-2">
                <button class="btn btn-success" onclick={() => { dispatch("copyClick", plan); }}><Fa icon={faCopy}/></button>
            </div>
            <div class="ms-2">
                <button onclick={() => { dispatch("deleteClick", plan); }} class="btn btn-danger"><Fa icon={faTrash}/></button>
            </div>
        {/if}
    </div>
    <div class="p-2 bg-light-three rounded collapse" class:show={expandedPlans[plan.id]}>
        {#await fetchViewForPlan(plan.view_id)}
            <div class="text-center text-muted p-2">Loading view...</div>
        {:then view}
            <div><a href="/view/{view.name}" class="btn btn-sm btn-primary"><Fa icon={faLink}/> View</a></div>
            <ViewDashboard bind:stats={planStats} productVersion={plan.target_version} {view}/>
        {/await}
    </div>
</div>

<style>
    .text-sm {
        font-size: 0.8em;
    }

    .w-10 {
        min-width: 10%;
    }
</style>
