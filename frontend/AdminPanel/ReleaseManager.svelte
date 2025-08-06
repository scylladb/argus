<script>
    import { onMount } from "svelte";
    import Fa from "svelte-fa";
    import {
        faAngleRight,
        faPlusCircle,
        faDolly,
    } from "@fortawesome/free-solid-svg-icons";
    import { sendMessage } from "../Stores/AlertStore";
    import ReleaseManagerGroup from "./ReleaseManagerGroup.svelte";
    import ReleaseManagerTest from "./ReleaseManagerTest.svelte";
    import BatchTestMover from "./BatchTestMover.svelte";
    import ReleaseCreator from "./ReleaseCreator.svelte";
    import GroupCreator from "./GroupCreator.svelte";
    import TestCreator from "./TestCreator.svelte";
    import ReleaseEditor from "./ReleaseEditor.svelte";
    let releases = $state([]);
    let currentRelease = $state();
    let currentReleaseId = $state();
    let currentReleaseData;
    let currentGroup = $state();
    let creatingRelease = $state(false);
    let editingRelease = $state(false);
    let creatingGroup = $state(false);
    let creatingTest = $state(false);
    let moving = $state(false);
    let fetching = $state(false);

    let groups = [];
    let tests = [];

    const fetchReleases = async function () {
        try {
            fetching = true;
            let apiResponse = await fetch("/admin/api/v1/releases/get");
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                releases = apiJson.response.sort((a, b) =>
                    a.name > b.name ? 1 : -1
                );
                if (releases.length > 0) {
                    if (!currentRelease?.id) {
                        currentRelease = releases[0];
                        currentReleaseId = currentRelease.id;
                    }
                }
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching releases.\nMessage: ${error.response.arguments[0]}`,
                    "ReleaseManager::fetch"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during releases fetch",
                    "ReleaseManager::fetch"
                );
            }
        } finally {
            fetching = false;
        }
    };

    const fetchReleaseGroups = async function (release) {
        let params = new URLSearchParams({
            releaseId: release.id,
        });
        try {
            let apiResponse = await fetch(
                "/admin/api/v1/groups/get?" + params.toString()
            );
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                groups = apiJson.response;
                return Promise.resolve(apiJson.response);
            } else {
                return Promise.reject(new Error(apiJson.message));
            }
        } catch (error) {
            console.log(error);
            return Promise.reject(error);
        }
    };

    const fetchGroupTests = async function (group) {
        let params = new URLSearchParams({
            groupId: group.id,
        });
        try {
            let apiResponse = await fetch(
                "/admin/api/v1/tests/get?" + params.toString()
            );
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                tests = apiJson.response;
                return Promise.resolve(apiJson.response);
            } else {
                return Promise.reject(new Error(apiJson.message));
            }
        } catch (error) {
            console.log(error);
            return Promise.reject(error);
        }
    };

    const apiMethodCall = async function (endpoint, body, method = "POST") {
        try {
            fetching = true;
            let apiResponse = await fetch(endpoint, {
                method: method,
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(body),
            });
            let res = await apiResponse.json();
            if (res.status === "ok") {
                return res;
            } else {
                throw res;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error.\nMessage: ${error.response.arguments[0]}`,
                    "ReleaseManager::apiMethodCall"
                );
            } else {
                sendMessage(
                    "error",
                    "Unhandled API Error occured. \nCheck response for details.",
                    "ReleaseManager::apiMethodCall"
                );
            }
        } finally {
            fetching = false;
        }
    };

    const handleReleaseSelection = function (e) {
        currentGroup = undefined;
        currentRelease = releases.find(
            (release) => release.id == currentReleaseId
        );
    };

    const handleGroupChange = function (group) {
        currentGroup = group;
    };

    const handleGroupCreate = async function (e) {
        creatingGroup = false;
        let result = await apiMethodCall(
            "/admin/api/v1/group/create",
            e.detail
        );
        if (result.status === "ok") {
            currentRelease = currentRelease;
        }
    };

    const handleGroupUpdate = async function (e) {
        creatingGroup = false;

        let result = await apiMethodCall(
            "/admin/api/v1/group/update",
            e.detail
        );
        if (result.status === "ok") {
            currentRelease = currentRelease;
        }
    };

    const handleGroupDelete = async function (e) {
        creatingGroup = false;
        let result = await apiMethodCall(
            "/admin/api/v1/group/delete",
            e.detail
        );
        if (result.status === "ok") {
            if (e.detail.group_id == currentGroup?.id) {
                currentGroup = undefined;
            }
            currentRelease = currentRelease;
        }
    };

    const handleGroupCreateCancel = function (e) {
        creatingGroup = false;
    };

    const handleTestsMove = async function (e) {
        moving = false;
        let result = await apiMethodCall(
            "/admin/api/v1/test/batch_move",
            e.detail
        );
        if (result.status === "ok") {
            currentGroup = currentGroup;
        }
    };

    const handleTestsMoveCancel = function (e) {
        moving = false;
    };

    const handleTestCreate = async function (e) {
        creatingTest = false;
        let result = await apiMethodCall("/admin/api/v1/test/create", e.detail);
        if (result.status === "ok") {
            currentGroup = currentGroup;
        }
    };

    const handleTestUpdate = async function (e) {
        creatingTest = false;
        let result = await apiMethodCall("/admin/api/v1/test/update", e.detail);
        if (result.status === "ok") {
            currentGroup = currentGroup;
        }
    };

    const handleTestDelete = async function (e) {
        creatingTest = false;
        let result = await apiMethodCall("/admin/api/v1/test/delete", e.detail);
        if (result.status === "ok") {
            currentGroup = currentGroup;
        }
    };

    const handleTestCreateCancel = function (e) {
        creatingTest = false;
    };

    const handleReleaseCreate = async function (e) {
        creatingRelease = false;
        let result = await apiMethodCall(
            "/admin/api/v1/release/create",
            e.detail
        );
        if (result.status === "ok") {
            fetchReleases();
        }
    };

    const handleReleaseCreateCancel = function (e) {
        creatingRelease = false;
    };


    const handleReleaseEdit = async function (e) {
        editingRelease = false;
        let result = await apiMethodCall(
            "/admin/api/v1/release/edit",
            e.detail
        );
        if (result.status === "ok") {
            fetchReleases();
        }
    };

    const handleReleaseDelete = async function (e) {
        editingRelease = false;
        currentRelease = undefined;
        let result = await apiMethodCall("/admin/api/v1/release/delete", e.detail);
        if (result.status === "ok") {
            fetchReleases();
        }
    };

    const handleReleaseEditCancel = function (e) {
        editingRelease = false;
    };



    const handleReleaseStateChange = async function (e) {
        let result = await apiMethodCall("/admin/api/v1/release/set_state", {
            release_id: currentReleaseId,
            state: currentRelease.enabled,
        });

        if (result.status === "ok") {
            fetchReleases();
        }
    };

    const handleReleaseDormancyChange = async function (e) {
        let result = await apiMethodCall("/admin/api/v1/release/set_dormant", {
            release_id: currentReleaseId,
            dormant: currentRelease.dormant,
        });

        if (result.status === "ok") {
            fetchReleases();
        }
    };

    const handleVisibilityToggle = async function(entity, type, state) {
        let result = await apiMethodCall(
            `/admin/api/v1/release/${type}/state/toggle`,
            {
                entityId: entity,
                state: state,
            }
        );
    };

    const handleReleasePerpetualityChange = async function (e) {
        let result = await apiMethodCall(
            "/admin/api/v1/release/set_perpetual",
            {
                release_id: currentReleaseId,
                perpetual: currentRelease.perpetual,
            }
        );

        if (result.status === "ok") {
            fetchReleases();
        }
    };

    onMount(() => {
        fetchReleases();
    });
</script>

<div class="bg-white m-2 p-2 rounded shadow-sm">
    <div class="row mb-2">
        <div class="col-4 px-2">
            <select
                class="form-select"
                bind:value={currentReleaseId}
                onchange={handleReleaseSelection}
            >
                {#each releases as release (release.id)}
                    <option value={release.id}
                        >{release.pretty_name || release.name}</option
                    >
                {/each}
            </select>
        </div>
        <div class="col-6 d-flex align-items-center">
            {#if currentRelease}
                <div class="form-check form-switch">
                    <input
                        class="form-check-input"
                        type="checkbox"
                        role="switch"
                        title="Whether this is a trunk branch, e.g. master"
                        bind:checked={currentRelease.perpetual}
                        onchange={handleReleasePerpetualityChange}
                        id="releaseManagerSwitchPerpetual"
                    />
                    <label
                        class="form-check-label"
                        for="releaseManagerSwitchPerpetual">Perpetual</label
                    >
                </div>
                <div class="ms-2 form-check form-switch">
                    <input
                        class="form-check-input"
                        type="checkbox"
                        role="switch"
                        title="Whether or not fetch stats for this release in some cases"
                        bind:checked={currentRelease.dormant}
                        onchange={handleReleaseDormancyChange}
                        id="releaseManagerSwitchDormant"
                    />
                    <label
                        class="form-check-label"
                        for="releaseManagerSwitchDormant">Dormant</label
                    >
                </div>
                <div class="ms-2 form-check form-switch">
                    <input
                        class="form-check-input"
                        type="checkbox"
                        role="switch"
                        title="Hide this release from Workspace and Releases page"
                        bind:checked={currentRelease.enabled}
                        onchange={handleReleaseStateChange}
                        id="releaseManagerSwitchEnabled"
                    />
                    <label
                        class="form-check-label"
                        for="releaseManagerSwitchEnabled">Enabled</label
                    >
                </div>
            {/if}
        </div>
        <div class="col-2 text-end d-flex align-items-center justify-content-end">
            {#if currentRelease}
                <div class="mx-2">
                    <button
                        class="btn btn-primary"
                        onclick={() => (editingRelease = true)}
                    >
                        Edit
                    </button>
                </div>
            {/if}
            {#if editingRelease}
                <ReleaseEditor
                    releaseData={currentRelease}
                    on:releaseEdit={handleReleaseEdit}
                    on:releaseEditCancel={handleReleaseEditCancel}
                    on:releaseDelete={handleReleaseDelete}
                />
            {/if}
            <button
                class="btn btn-success"
                onclick={() => (creatingRelease = true)}
            >
                New Release
            </button>
            {#if creatingRelease}
                <ReleaseCreator
                    on:releaseCreateCancel={handleReleaseCreateCancel}
                    on:releaseCreate={handleReleaseCreate}
                />
            {/if}
        </div>
    </div>
    {#if fetching}
        <div class="row border-top mt-2">
            <div class="col">
                <div class="d-flex align-items-center justify-content-center bg-white py-4">
                    <span class="spinner-border spinner-border-sm"></span> <span class="ms-2">Working...</span>
                </div>
            </div>
        </div>
    {/if}
    {#if currentRelease}
        {#await fetchReleaseGroups(currentRelease)}
            <row class="border-top mt-2">
                <div class="col">
                    <div class="text-muted text-center mt-4">
                        <span class="spinner-border spinner-border-sm"></span> Loading...
                    </div>
                </div>
            </row>
        {:then releaseGroups}
            <div class="row border-top mt-2 manager-row">
                <div class="col-6">
                    <div class="d-flex align-items-center my-2">
                        <div class="fw-bold">Groups</div>
                        <div class="ms-auto">
                            <button
                                class="ms-2 btn btn-sm btn-success"
                                title="Create new"
                                onclick={() => (creatingGroup = true)}
                            >
                                New Group
                            </button>
                            {#if creatingGroup}
                                <GroupCreator
                                    releaseId={currentReleaseId}
                                    on:groupCreate={handleGroupCreate}
                                    on:groupCreateCancel={handleGroupCreateCancel}
                                />
                            {/if}
                        </div>
                    </div>
                    <ul class="list-group manager-list">
                        {#each releaseGroups.sort((a, b) => a.name > b.name ? 1 : -1) as group (group.id)}
                            <li
                                class="list-group-item d-flex"
                                role="button"
                                class:selected={currentGroup?.id == group.id}
                                onclick={() => handleGroupChange(group)}
                            >
                                <ReleaseManagerGroup
                                    {group}
                                    groups={releaseGroups}
                                    on:groupDelete={handleGroupDelete}
                                    on:groupUpdate={handleGroupUpdate}
                                    on:visibilityToggleGroup={(e) => {
                                        handleVisibilityToggle(e.detail.groupId, "group", e.detail.enabled);
                                    }}
                                />
                            </li>
                        {/each}
                    </ul>
                </div>
                {#if currentGroup}
                    <div class="col-6">
                        {#await fetchGroupTests(currentGroup)}
                            <div class="text-center text-muted mt-4">
                                <span class="spinner-border spinner-border-sm"></span> Loading...
                            </div>
                        {:then groupTests}
                            <div class="d-flex align-items-center mb-2 my-2">
                                <div class="fw-bold">Tests</div>
                                <button
                                    class="ms-2 btn btn-sm btn-success"
                                    title="Batch move"
                                    onclick={() => (moving = true)}
                                    ><Fa icon={faDolly} /></button
                                >
                                {#if moving}
                                    <BatchTestMover
                                        groups={releaseGroups}
                                        tests={groupTests}
                                        on:testsMoveCancel={handleTestsMoveCancel}
                                        on:testsMove={handleTestsMove}
                                    />
                                {/if}
                                <div class="ms-auto">
                                    <button
                                        class="ms-2 btn btn-sm btn-success"
                                        title="Create new"
                                        onclick={() => (creatingTest = true)}
                                        >New Test</button
                                    >
                                    {#if creatingTest}
                                        <TestCreator
                                            groups={releaseGroups}
                                            releaseId={currentReleaseId}
                                            groupId={currentGroup.id}
                                            on:testCreate={handleTestCreate}
                                            on:testCreateCancel={handleTestCreateCancel}
                                        />
                                    {/if}
                                </div>
                            </div>
                            <ul class="list-group manager-list">
                                {#each groupTests.sort((a, b) => a.name > b.name ? 1 : -1) as test (test.id)}
                                    <ReleaseManagerTest
                                        {test}
                                        groups={releaseGroups}
                                        on:testUpdate={handleTestUpdate}
                                        on:testDelete={handleTestDelete}
                                        on:visibilityToggleTest={(e) => {
                                            handleVisibilityToggle(e.detail.testId, "test", e.detail.enabled);
                                        }}
                                    />
                                {/each}
                            </ul>
                        {:catch error}
                            <div class="text-muted text-center p-2">
                                Error loading tests for group {currentGroup.pretty_name || currentGroup.name}: {error.message}
                            </div>
                        {/await}
                    </div>
                {/if}
            </div>
        {:catch error}
            <div class="text-muted text-center p-2">
                Error loading groups for release {currentRelease.name}: {error.message}
            </div>
        {/await}
    {/if}
</div>

<style>
    .manager-list {
        min-height: 480px;
        max-height: 720px;
        overflow-y: scroll;
    }

    .manager-row {
        min-height: 480px;
        max-height: 900px;
    }

    .selected {
        background-color: rgb(95, 201, 81);
    }
</style>
