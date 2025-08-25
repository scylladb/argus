<script lang="ts">
    import Select from "svelte-select";
    import User from "../Profile/User.svelte";
    import { createEventDispatcher, onMount } from "svelte";
    import ViewSelectItem from "../AdminPanel/ViewSelectItem.svelte";
    import { titleCase } from "../Common/TextUtils";
    import queryString from "query-string";
    import { ADD_ALL_ID } from "../Common/ViewTypes";
    import Fa from "svelte-fa";
    import { faExclamationCircle, faExpand, faTrash, faThLarge } from "@fortawesome/free-solid-svg-icons";
    import { sendMessage } from "../Stores/AlertStore";
    import ModalWindow from "../Common/ModalWindow.svelte";
    import ReleasePlannerGridView from "./ReleasePlannerGridView.svelte";
    import { filterUser } from "../Common/SelectUtils";
    import ViewSelect from "../Views/ViewSelect.svelte";


    let gridViewOpen = $state(false);
    let users = $state([]);
    let testSearcherValue = $state();
    let lastHits = [];
    let participants = $state([]);
    let items = $state([]);
    let views = $state([]);
    const dispatch = createEventDispatcher();

    const TYPE_MARKER = {
        "release": "bg-primary",
        "group": "bg-success",
        "test": "bg-dark",
    };

    const NEW_PLAN_TEMPLATE = {
        name: "",
        description: "",
        owner:  undefined,
        participants: [],
        target_version: "",
        release_id: release.id,
        tests: [],
        groups: [],
        assignments: {},
    };

    let PLAN_VALIDATION_RULES = $state({
        name: {
            validated: true,
            soft: false,
            message: "Name must not be empty",
            validate: (plan) => plan.name != "",
        },
        description: {
            validated: true,
            soft: true,
            message: "Description is empty",
            validate: (plan) => plan.description != "",
        },
        owner: {
            validated: true,
            soft: false,
            message: "Plan must have an owner",
            validate: (plan) => !!plan.owner,
        },
        participants: {
            validated: true,
            message: "",
            soft: false,
            validate: function (plan) {
                let assignedParticipants = Object.values(plan.assignments);
                let missing = [];
                for (const user of plan.participants) {
                    if (!assignedParticipants.find(v => v == user))  {
                        const username = users.find(v => v.id == user)?.username || user;
                        missing.push(`@${username}`);
                    }
                }
                if (missing.length > 0) {
                    this.message = `User(s) ${missing.join(", ")} participating but not assigned.`;
                    return false;
                }
                return true;
            }
        },
        target_version: {
            validated: true,
            soft: true,
            message: "The version has not been specified. Plan will apply for any matched test if a version plan is not found.",
            validate: (plan) => plan.target_version != "",
        },
        tests: {
            validated: true,
            soft: false,
            message: "No tests or groups have been selected",
            validate: (plan) => plan.tests.length > 0 || plan.groups.length > 0,
        },
        groups: {
            validated: true,
            soft: false,
            message: "No tests or groups have been selected",
            validate: (plan) => plan.tests.length > 0 || plan.groups.length > 0,
        }
    });


    const createPlan = async function () {
        try {
            let planPayload = {
                name: plan.name,
                description: plan.description,
                owner: plan.owner,
                participants: plan.participants,
                target_version: plan.target_version,
                release_id: plan.release_id,
                view_id: plan.view_id,
                tests: plan.tests,
                groups: plan.groups,
                assignments: plan.assignments,
                created_from: plan.id,
            };

            const response = await fetch("/api/v1/planning/plan/create", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(planPayload),
            });

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            dispatch("planCreated");
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when creating a plan.\nMessage: ${error.response.arguments[0]}`,
                    "ReleasePlanCreator::create"
                );
            } else if (error?.cause == "validation") {
                console.log("Validation failed...");
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during plan creation",
                    "ReleasePlanCreator::create"
                );
                console.log(error);
            }
        } finally {
            // empty
        }
    };

    const updatePlan = async function () {
        const oldAssignmentState = Object.assign({}, plan.assignments);
        try {
            plan.assignee_mapping = plan.assignments;
            delete plan.assignments;
            const response = await fetch("/api/v1/planning/plan/update", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(plan),
            });

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            dispatch("planUpdated");
        } catch (error) {
            plan.assignments = Object.assign({}, oldAssignmentState);
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when updating a plan.\nMessage: ${error.response.arguments[0]}`,
                    "ReleasePlanCreator::create"
                );
            } else if (error?.cause == "validation") {
                console.log("Validation failed...");
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during plan update",
                    "ReleasePlanCreator::create"
                );
                console.log(error);
            }
        } finally {
            // empty
        }
    };

    const handleCreatePlan = function() {
        plan.participants = participants ? participants.map(v => v.id) : [];
        plan.tests = items.filter(v => v.type == "test").map(v => v.id);
        plan.groups = items.filter(v => v.type == "group").map(v => v.id);
        validatePlan(plan);
        if (checkValidation()) {
            createPlan();
        }
    };

    const handleUpdatePlan = function() {
        plan.participants = participants ? participants.map(v => v.id) : [];
        plan.tests = items.filter(v => v.type == "test").map(v => v.id);
        plan.groups = items.filter(v => v.type == "group").map(v => v.id);
        validatePlan(plan);
        if (checkValidation()) {
            updatePlan();
        }
    };

    const checkValidation = function() {
        for (const rule of Object.values(PLAN_VALIDATION_RULES)) {
            if (!rule.validated && !rule.soft) {
                return false;
            }
        }
        return true;
    };

    const validatePlan = function(plan) {
        for (const rule of Object.values(PLAN_VALIDATION_RULES)) {
            rule.validated = rule.validate(plan);
        }
        PLAN_VALIDATION_RULES = PLAN_VALIDATION_RULES;
    };

    /**
     * @param {string} query
     */
    const testLookup = async function (query) {
        try {
            const params = {
                query: query,
                releaseId: release.id,
            };
            const qs = queryString.stringify(params);
            const response = await fetch("/api/v1/planning/search?" + qs);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }
            lastHits = json.response.hits;
            return json.response.hits.slice(0, 100);

        } catch (error) {
            console.log(error);
        }
    };

    const getAllViews = async function () {
        try {
            const response = await fetch("/api/v1/views/all");
            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }
            views = json.response;
            return views;

        } catch (error) {
            console.log(error);
        }
    };

    const resolvePlan = async function (plan) {
        try {
            const response = await fetch(`/api/v1/planning/plan/${plan.id}/resolve_entities`);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            return json.response;

        } catch (error) {
            console.log(error);
        }
    };

    /**
     * @param {string} query
     */
    const explodeGroup = async function (groupId) {
        try {
            const response = await fetch(`/api/v1/planning/group/${groupId}/explode`);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }
            items = items.filter(v => v.id != groupId);
            items = [...items, ...json.response];
            if (plan.assignments[groupId]) {
                json.response.forEach(v => plan.assignments[v.id] = plan.assignments[groupId]);
                delete plan.assignments[groupId];
            }

        } catch (error) {
            console.log(error);
        }
    };

    const handleAllItemSelect = function() {
        items = [
            ...items,
            ...lastHits
                .filter(i => i.id != ADD_ALL_ID
                ).map(item => {
                    return {
                        name: item.pretty_name || item.name,
                        release: item.release?.name,
                        group: item.group?.pretty_name || item.group?.name,
                        type: item.type,
                        id: item.id,
                    };
                })];
        testSearcherValue = undefined;
    };

    const handleItemSelect = function(e) {
        const item = e.detail;
        if (item.id == ADD_ALL_ID) return handleAllItemSelect();
        items = [...items, {
            name: item.pretty_name || item.name,
            release: item.release?.name,
            group: item.group?.pretty_name || item.group?.name,
            type: item.type,
            id: item.id,
        }];
        testSearcherValue = undefined;
    };

    const removeSelectedItem = function(id) {
        items = items.filter(v => v.id != id);
    };


    const handleClearAll = function() {
        items = [];
        plan.assignments = {};
    };


    const handleGridConfirmation = function(e) {
        const selectedItems = e.detail.items;
        selectedItems.forEach((item) => {
            if (!items.find(i => i.id == item.id)) {
                items.push(item);
            }
        });
        items = items;
        gridViewOpen = false;
    };

    const getUsers = async function () {
        try {
            const response = await fetch("/api/v1/users");

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }
            users = Object.values(json.response);
            return users;

        } catch (error) {
            console.log(error);
        }
    };


    const fetchVersions = async function() {
        let response = await fetch(`/api/v1/release/${release.id}/versions`);
        if (response.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await response.json();
        if (json.status !== "ok") {
            return Promise.reject(json.exception);
        }

        return json.response;
    };

    interface Props {
        release: any;
        plans?: any;
        mode?: string;
        plan?: any;
    }

    let {
        release,
        plans = [],
        mode = "create",
        plan = $bindable(Object.assign({}, NEW_PLAN_TEMPLATE))
    }: Props = $props();

    onMount(async () => {
        await getUsers();
        await getAllViews();
        if (mode == "edit" || mode == "createFrom") {
            plan.assignments = plan.assignee_mapping;
            participants = users.filter(u => plan.participants.includes(u.id));
            items = await resolvePlan(plan);
        }
        if (mode == "createFrom" && !plan.created_from) {
            plan.created_from = plan.id;
        }
    });
</script>


{#if gridViewOpen}
    <ModalWindow widthClass="w-75" on:modalClose={() => (gridViewOpen = false)}>
        {#snippet title()}
                <div >Grid View</div>
            {/snippet}
        {#snippet body()}
                <div >
                <ReleasePlannerGridView existingPlans={plans} {release} selectingFor={plan} on:gridViewConfirmed={handleGridConfirmation}/>
            </div>
            {/snippet}
    </ModalWindow>
{/if}


<div>
    {#if !PLAN_VALIDATION_RULES["name"].validated}
        <div class="alert alert-{PLAN_VALIDATION_RULES["name"].soft ? "warning" : "danger" } mb-2 rounded border p-2">
            <Fa icon={faExclamationCircle} /> {PLAN_VALIDATION_RULES["name"].message}
        </div>
    {/if}
    <div class="d-flex align-items-center mb-2">
        <div class="w-25 fw-bold me-2">Name</div>
        <div class="flex-fill">
            <input class="form-control" type="text" id="ReleasePlanName" bind:value={plan.name}>
        </div>
    </div>
    {#if !PLAN_VALIDATION_RULES["description"].validated}
        <div class="alert alert-{PLAN_VALIDATION_RULES["description"].soft ? "warning" : "danger" } mb-2 rounded border p-2">
            <Fa icon={faExclamationCircle} /> {PLAN_VALIDATION_RULES["description"].message}
        </div>
    {/if}
    <div class="d-flex align-items-center mb-2">
        <div class="w-25 fw-bold me-2 align-self-start">Description</div>
        <div class="flex-fill">
            <textarea class="form-control w-100" id="ReleasePlanDescription" bind:value={plan.description} cols="0" rows="5" placeholder=""></textarea>
        </div>
    </div>
    {#if !PLAN_VALIDATION_RULES["owner"].validated}
        <div class="alert alert-{PLAN_VALIDATION_RULES["owner"].soft ? "warning" : "danger" } mb-2 rounded border p-2">
            <Fa icon={faExclamationCircle} /> {PLAN_VALIDATION_RULES["owner"].message}
        </div>
    {/if}
    <div class="d-flex align-items-center mb-2">
        <div class="w-25 fw-bold me-2">Owner</div>
        <div class="flex-fill">
            <Select
                --item-height="auto"
                --item-line-height="auto"
                value={users.find(u => u.id == plan.owner)}
                on:select={(e) => plan.owner = e.detail.id}
                items={users}
                itemFilter={filterUser}
                label="username"
                itemId="id"
            >
                <div slot="item" let:item let:index>
                    <User {item} />
                </div>
            </Select>
        </div>
    </div>
    {#if !PLAN_VALIDATION_RULES["target_version"].validated}
        <div class="alert alert-{PLAN_VALIDATION_RULES["target_version"].soft ? "warning" : "danger" } mb-2 rounded border p-2">
            <Fa icon={faExclamationCircle} /> {PLAN_VALIDATION_RULES["target_version"].message}
        </div>
    {/if}
    <div class="d-flex align-items-center mb-2">
        <datalist id="version-autocomplete">
            {#await fetchVersions()}
                <!-- promise is pending -->
            {:then autocompleteVersions}
                {#each autocompleteVersions as val}
                    <option value="{val}"></option>
                {/each}
            {/await}
        </datalist>
        <div class="w-25 fw-bold me-2">Target Version</div>
        <div class="flex-fill">
            <input class="form-control" type="text" id="ReleasePlanVersionField" list="version-autocomplete" bind:value={plan.target_version}>
        </div>
    </div>
    {#if !PLAN_VALIDATION_RULES["participants"].validated}
        <div class="alert alert-{PLAN_VALIDATION_RULES["participants"].soft ? "warning" : "danger" } mb-2 rounded border p-2">
            <Fa icon={faExclamationCircle} /> {PLAN_VALIDATION_RULES["participants"].message}
        </div>
    {/if}
    <div class="d-flex align-items-center mb-2">
        <div class="w-25 fw-bold me-2">Participants</div>
        <div class="flex-fill">
            <Select
                --item-height="auto"
                --item-line-height="auto"
                bind:value={participants}
                items={users}
                itemFilter={filterUser}
                multiple={true}
                label="username"
                itemId="id"
            >
                <div slot="item" let:item let:index>
                    <User {item} />
                </div>
            </Select>
        </div>
    </div>
    <div class="d-flex align-items-center mb-2">
        <div class="w-25 fw-bold me-2">Existing view</div>
        <div class="flex-fill">
            <Select
                value={views.find(p => p.id == plan.view_id)}
                on:select={(e) => plan.view_id = e.detail.id}
                items={views}
                label="display_name"
                itemId="id"
            >
                <div slot="item" let:item let:index>
                    <ViewSelect {item} />
                </div>
            </Select>
        </div>
    </div>
    <div class="mb-2">
        <div class="d-flex align-items-center">
            <div class="flex-fill">
                <Select
                    id="viewSelectComponent"
                    inputAttributes={{ class: "form-control" }}
                    bind:value={testSearcherValue}
                    placeholder="Search for tests..."
                    label="name"
                    itemId="id"
                    loadOptions={testLookup}
                    on:select={handleItemSelect}
                >
                    <div class="text-muted text-center p-2">
                        Type to search. Can be: Test name, Release name, Group name.
                    </div>
                    <div slot="item" let:item let:index>
                        <ViewSelectItem {item} />
                    </div>
                </Select>
            </div>
            <button class="ms-2 btn btn-primary" onclick={() => (gridViewOpen = true)}>
                <Fa icon={faThLarge}/>
            </button>
        </div>
    </div>
    {#if !PLAN_VALIDATION_RULES["tests"].validated}
        <div class="alert alert-{PLAN_VALIDATION_RULES["tests"].soft ? "warning" : "danger" } mb-2 rounded border p-2">
            <Fa icon={faExclamationCircle} /> {PLAN_VALIDATION_RULES["tests"].message}
        </div>
    {/if}
    {#if !PLAN_VALIDATION_RULES["groups"].validated}
        <div class="alert alert-{PLAN_VALIDATION_RULES["groups"].soft ? "warning" : "danger" } mb-2 rounded border p-2">
            <Fa icon={faExclamationCircle} /> {PLAN_VALIDATION_RULES["groups"].message}
        </div>
    {/if}
    <div class="border form-control mb-2 bg-light-three" style="min-height: 192px; max-height: 768px; overflow-y: scroll">
        {#if items.length > 0}
            <div class="mb-2">
                <button onclick={handleClearAll} class="w-100 btn btn-sm btn-danger"><Fa icon={faTrash}/>Remove all</button>
            </div>
        {/if}
        {#each items as item}
            <div class="p-2 border rounded bg-white mb-1 d-flex align-items-center">
                <div
                    class="{TYPE_MARKER[item.type] ?? "bg-danger"} rounded p-2 fw-bold text-white"
                    title={titleCase(item.type)}
                >
                    {titleCase(item.type).at(0)}
                </div>
                <div class="ms-2">
                    {item.pretty_name || item.display_name || item.name}
                    {#if item.release}
                        <div class="text-muted text-sm">{item.release}</div>
                    {/if}
                    {#if item.group}
                        <div class="text-muted text-sm">{item.group}</div>
                    {/if}
                </div>
                <div class="ms-auto" style="min-width: 192px">
                    <Select
                        --item-height="auto"
                        --item-line-height="auto"
                        value={users.find(u => u.id == plan?.assignments?.[item.id])}
                        placeholder="Owner"
                        on:select={(e) => plan.assignments[item.id] = e.detail.id}
                        on:clear={() => {
                            delete plan.assignments[item.id];
                            plan = plan;
                        }}
                        items={participants}
                        itemFilter={filterUser}
                        label="username"
                        itemId="id"
                    >
                        <div slot="item" let:item let:index>
                            <User {item} />
                        </div>
                    </Select>
                </div>
                {#if item.type == "group"}
                    <button class="ms-2 btn btn-sm btn-primary" onclick={() => explodeGroup(item.id)}><Fa icon={faExpand}/></button>
                {/if}
                <button class="ms-2 btn btn-sm btn-warning" onclick={() => removeSelectedItem(item.id)}><Fa icon={faTrash}/></button>
            </div>
        {:else}
            <option value="!!">No tests selected.</option>
        {/each}
    </div>
    <div>
        {#if mode != "edit"}
            <button class="btn btn-success w-100" onclick={handleCreatePlan}>Create</button>
        {:else}
            <button class="btn btn-warning w-100" onclick={handleUpdatePlan}>Edit</button>
        {/if}
    </div>
</div>

<style>
    .text-sm {
        font-size: 0.8em;
    }
</style>
