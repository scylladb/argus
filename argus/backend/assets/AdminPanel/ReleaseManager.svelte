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
    let releases = [];
    let currentRelease;
    let currentReleaseId;
    let currentReleaseData;
    let currentGroup;
    let creatingRelease = false;
    let creatingGroup = false;
    let creatingTest = false;
    let moving = false;
    let fetching = false;

    const fetchReleases = async function () {
        try {
            fetching = true;
            let apiResponse = await fetch("/api/v1/releases?all=true");
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                releases = apiJson.response;
                if (releases.length > 0) {
                    if (!currentRelease?.id) {
                        currentRelease = releases[0];
                        currentReleaseId = currentRelease.id;
                    }
                    fetchReleaseData(currentRelease.id);
                }
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching releases.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during releases fetch"
                );
            }
        } finally {
            fetching = false;
        }
    };

    const fetchReleaseData = async function (id) {
        currentReleaseData = undefined;
        try {
            fetching = true;
            let params = new URLSearchParams({
                releaseId: id,
            });
            let apiResponse = await fetch(
                "/api/v1/release/planner/data?" + params,
                {
                    method: "GET",
                }
            );
            let apiJson = await apiResponse.json();
            if (apiJson.status === "ok") {
                currentReleaseData = apiJson.response ?? {};
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `Unable to fetch release data.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during release data fetch"
                );
            }
        } finally {
            fetching = false;
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
                    `API Error.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "Unhandled API Error occured. \nCheck response for details."
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
        fetchReleaseData(currentRelease.id);
    };

    const handleGroupChange = function (id) {
        currentGroup = id;
    };

    const handleGroupCreate = async function (e) {
        creatingGroup = false;
        let result = await apiMethodCall(
            "/admin/api/v1/group/create",
            e.detail
        );
        if (result.status === "ok") {
            fetchReleaseData(currentRelease.id);
        }
    };

    const handleGroupUpdate = async function (e) {
        creatingGroup = false;
        let result = await apiMethodCall(
            "/admin/api/v1/group/update",
            e.detail
        );
        if (result.status === "ok") {
            fetchReleaseData(currentRelease.id);
        }
    };

    const handleGroupDelete = async function (e) {
        creatingGroup = false;
        let result = await apiMethodCall(
            "/admin/api/v1/group/delete",
            e.detail
        );
        if (result.status === "ok") {
            fetchReleaseData(currentRelease.id);
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
            fetchReleaseData(currentRelease.id);
        }
    };

    const handleTestsMoveCancel = function (e) {
        moving = false;
    };

    const handleTestCreate = async function (e) {
        creatingTest = false;
        let result = await apiMethodCall("/admin/api/v1/test/create", e.detail);
        if (result.status === "ok") {
            fetchReleaseData(currentRelease.id);
        }
    };

    const handleTestUpdate = async function (e) {
        creatingTest = false;
        let result = await apiMethodCall("/admin/api/v1/test/update", e.detail);
        if (result.status === "ok") {
            fetchReleaseData(currentRelease.id);
        }
    };

    const handleTestDelete = async function (e) {
        creatingTest = false;
        let result = await apiMethodCall("/admin/api/v1/test/delete", e.detail);
        if (result.status === "ok") {
            fetchReleaseData(currentRelease.id);
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
                on:change={handleReleaseSelection}
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
                        on:change={handleReleasePerpetualityChange}
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
                        on:change={handleReleaseDormancyChange}
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
                        on:change={handleReleaseStateChange}
                        id="releaseManagerSwitchEnabled"
                    />
                    <label
                        class="form-check-label"
                        for="releaseManagerSwitchEnabled">Enabled</label
                    >
                </div>
            {/if}
        </div>
        <div class="col-2 text-end">
            <button
                class="btn btn-success"
                on:click={() => (creatingRelease = true)}
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
                <div class="text-center bg-white py-4">
                    <span class="spinner-border" /> Loading...
                </div>
            </div>
        </div>
    {/if}
    {#if currentRelease && currentReleaseData}
        <div class="row border-top mt-2 manager-row">
            <div class="col-5">
                <div class="d-flex align-items-center my-2">
                    <div class="fw-bold">Groups</div>
                    <div class="ms-auto">
                        <button
                            class="ms-2 btn btn-sm btn-success"
                            title="Create new"
                            on:click={() => (creatingGroup = true)}
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
                    {#each Object.values(currentReleaseData.groups) as group (group.id)}
                        <li
                            class="list-group-item d-flex"
                            role="button"
                            class:active={currentGroup == group.id}
                            on:click={() => handleGroupChange(group.id)}
                        >
                            <ReleaseManagerGroup
                                {group}
                                groups={Object.values(
                                    currentReleaseData.groups
                                )}
                                on:groupDelete={handleGroupDelete}
                                on:groupUpdate={handleGroupUpdate}
                            />
                        </li>
                    {/each}
                </ul>
            </div>
            {#if currentGroup}
                <div
                    class="col-1 d-flex fs-1 align-items-top justify-content-center"
                >
                    <Fa icon={faAngleRight} />
                </div>
                <div class="col-5">
                    <div class="d-flex align-items-center mb-2 my-2">
                        <div class="fw-bold">Tests</div>
                        <button
                            class="ms-2 btn btn-sm btn-success"
                            title="Batch move"
                            on:click={() => (moving = true)}
                            ><Fa icon={faDolly} /></button
                        >
                        {#if moving}
                            <BatchTestMover
                                groups={Object.values(
                                    currentReleaseData.groups
                                )}
                                tests={currentReleaseData.tests_by_group[
                                    currentReleaseData.groups[currentGroup].name
                                ]}
                                on:testsMoveCancel={handleTestsMoveCancel}
                                on:testsMove={handleTestsMove}
                            />
                        {/if}
                        <div class="ms-auto">
                            <button
                                class="ms-2 btn btn-sm btn-success"
                                title="Create new"
                                on:click={() => (creatingTest = true)}
                                >New Test</button
                            >
                            {#if creatingTest}
                                <TestCreator
                                    groups={Object.values(
                                        currentReleaseData.groups
                                    )}
                                    releaseId={currentReleaseId}
                                    groupId={currentGroup}
                                    on:testCreate={handleTestCreate}
                                    on:testCreateCancel={handleTestCreateCancel}
                                />
                            {/if}
                        </div>
                    </div>
                    <ul class="list-group manager-list">
                        {#each currentReleaseData.tests_by_group[currentReleaseData.groups[currentGroup].name] ?? [] as test (test.id)}
                            <ReleaseManagerTest
                                {test}
                                releaseData={currentReleaseData}
                                on:testUpdate={handleTestUpdate}
                                on:testDelete={handleTestDelete}
                            />
                        {/each}
                    </ul>
                </div>
            {/if}
        </div>
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
</style>
