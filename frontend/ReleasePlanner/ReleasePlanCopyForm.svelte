<script lang="ts">
    import queryString from "query-string";
    import { sendMessage } from "../Stores/AlertStore";
    import Fa from "svelte-fa";
    import { faCheck, faTimes } from "@fortawesome/free-solid-svg-icons";
    import EntityReplacer from "./EntityReplacer.svelte";
    import Select from "svelte-select";
    import User from "../Profile/User.svelte";
    import { createEventDispatcher, onMount } from "svelte";
    import { filterUser } from "../Common/SelectUtils";

    let { plan, release = $bindable() } = $props();
    const dispatch = createEventDispatcher();
    let users = $state([]);

    let selectedRelease = $state(release.id);
    let lastCheck = $state();
    let copy = $state(Object.assign({}, plan));
    let keepAssignees = $state(false);
    let replacements = $state({});

    const fetchReleases = async function() {
        try {
            const response = await fetch("/api/v1/releases");

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            return json.response.filter(v => v.id != release.id);

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching releases.\nMessage: ${error.response.arguments[0]}`,
                    "ReleasePlannerCopy::fetchReleases"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during release copy release fetch",
                    "ReleasePlannerCopy::fetchReleases"
                );
                console.log(error);
            }
        }
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
        let response = await fetch(`/api/v1/release/${lastCheck?.targetRelease?.id ?? plan.release_id}/versions`);
        if (response.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await response.json();
        if (json.status !== "ok") {
            return Promise.reject(json.exception);
        }

        return json.response;
    };


    let versionsPromise = $state(fetchVersions());


    const checkElegible = async function(releaseId) {
        try {
            const params = {
                releaseId: releaseId
            };
            const qs = queryString.stringify(params);
            const response = await fetch(`/api/v1/planning/plan/${plan.id}/copy/check?` + qs);

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }
            lastCheck = json.response;
            versionsPromise = fetchVersions();
            return json.response;

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when checking elegible release.\nMessage: ${error.response.arguments[0]}`,
                    "ReleasePlannerCopy::checkEligible"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during elegibility check",
                    "ReleasePlannerCopy::checkEligible"
                );
                console.log(error);
            }
        }
    };

    const handleReplacements = function(e) {
        const { original, replacement } = e.detail;
        replacements[original.id] = replacement.id;
    };

    let elegiblePromise = $state(checkElegible(selectedRelease));

    onMount(async () => {
        getUsers();
    });
</script>

<div>
    <div class="row mb-2">
        <div class="col-6">
            <h6>Original Release</h6>
            <div>
                <input type="text" class="form-control" disabled bind:value={release.name}>
            </div>
        </div>
        <div class="col-6">
            <h6>Target Release</h6>
            <div>
                <select class="form-control form-select" bind:value={selectedRelease} onchange={() => {
                    elegiblePromise = checkElegible(selectedRelease);
                }}>
                    <option value="{release.id}">{release.name}</option>
                    {#await fetchReleases()}
                        <option value="null">Loading...</option>
                    {:then releases}
                        {#each releases as release (release.id)}
                            <option value="{release.id}">{release.name}</option>
                        {/each}
                    {/await}
                </select>
            </div>
        </div>
    </div>
    <div class="row mb-2">
        <div class="col">
            <label for="" class="form-label">New name</label>
            <input type="text" class="form-control" bind:value={copy.name}>
        </div>
    </div>
    <div class="row mb-2">
        <div class="col">
            <datalist id="version-autocomplete">
                {#await versionsPromise}
                    <!-- promise is pending -->
                {:then autocompleteVersions}
                    {#each autocompleteVersions as val}
                        <option value="{val}"></option>
                    {/each}
                {/await}
            </datalist>
            <label for="ReleasePlanVersionField" class="form-label">New Version</label>
            <input class="form-control" type="text" id="ReleasePlanVersionField" list="version-autocomplete" bind:value={copy.target_version}>
        </div>
    </div>
    <div class="row mb-2">
        <div class="col d-flex flex-column">
            <label for="" class="form-label">New description</label>
            <textarea class="form-control" id="" cols="0" rows="4" bind:value={copy.description}></textarea>
        </div>
    </div>
    <div class="row mb-2">
        <div class="col d-flex flex-column">
            <div class="ms-2 form-check form-switch">
                <input
                    class="form-check-input"
                    type="checkbox"
                    role="switch"
                    title=""
                    bind:checked={keepAssignees}
                    id="copyFormKeepAssignments"
                />
                <label
                    class="form-check-label"
                    for="copyFormKeepAssignments">Keep previous participants</label
                >
            </div>
        </div>
    </div>
    <div class="row mb-2">
        <div class="col d-flex flex-column">
            <label for="" class="form-label">Owner</label>
            <Select
                --item-height="auto"
                --item-line-height="auto"
                inputAttributes={{ class: "form-control" }}
                value={users.find(u => u.id == plan.owner)}
                on:select={(e) => copy.owner = e.detail.id}
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
    <div class="row my-4">
        {#await elegiblePromise}
            <div class="col text-center p-2 d-flex align-items-center justify-content-center">
                <span class="spinner-border text-dark" role="status"></span>
                <div class="ms-2">Checking Eligibility...</div>
            </div>
        {:then checkResult}
            {#if checkResult.status == "passed"}
                <div class="col text-center mb-2 p-2 d-flex align-items-center justify-content-center">
                    <Fa class="text-success" icon={faCheck} /> Checks passed. Ready to copy.
                </div>
            {:else}
                <div class="col">
                    <div class="text-center mb-2"><Fa class="text-danger" icon={faTimes} /> Some entities are missing from target. If you wish to continue, they will be dropped.</div>
                    <div>
                        <div class="row">
                            <div class="col-6">
                                <h6>Missing tests</h6>
                                {#each checkResult.missing.tests as test (test.id)}
                                    <EntityReplacer entity={test} targetRelease={checkResult.targetRelease} on:entityReplaced={handleReplacements}/>
                                {:else}
                                    <div class="p-2 text-center text-muted">
                                        No tests are missing.
                                    </div>
                                {/each}
                            </div>
                            <div class="col-6">
                                <h6>Missing groups</h6>
                                {#each checkResult.missing.groups as group (group.id)}
                                    <EntityReplacer entity={group} targetRelease={checkResult.targetRelease} entityType="group" on:entityReplaced={handleReplacements}/>
                                {:else}
                                    <div class="p-2 text-center text-muted">
                                        No groups are missing.
                                    </div>
                                {/each}
                            </div>
                        </div>
                    </div>
                </div>
            {/if}
        {/await}
    </div>
    <div class="row mb-2">
        <div class="col d-flex">
            <button class="w-75 btn btn-primary" onclick={() => dispatch("copyConfirmed", {
                plan: copy,
                keepParticipants: keepAssignees,
                replacements: replacements,
                targetReleaseId: lastCheck.targetRelease.id,
                targetReleaseName: lastCheck.targetRelease.name,
            })}>Copy</button>
            <button class="ms-2 w-25 btn btn-secondary" onclick={() => dispatch("copyCanceled")}>Cancel</button>
        </div>
    </div>
</div>
