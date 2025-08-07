<script lang="ts">
    import Fa from "svelte-fa";
    import {
        faExternalLinkAlt,
        faTasks,
    } from "@fortawesome/free-solid-svg-icons";
    import { stateEncoder } from "../Common/StateManagement";
    let { schedules = [] } = $props();
    const generateJenkinsGroupUrl = function(details, releaseDetails) {
        const baseURL = "https://jenkins.scylladb.com/";
        let group = details;
        let release = releaseDetails;
        return `${baseURL}job/${release?.name}/job/${group?.name}`;
    };

    const sortByStartTime = function () {
        return [...schedules].sort((a, b) => {
            let leftDate = new Date(a.period_start);
            let rightDate = new Date(b.period_start);
            if (leftDate > rightDate) {
                return 1;
            } else if (rightDate > leftDate) {
                return -1;
            }
            return 0;
        });
    };

    const prepareState = function (schedule) {
        return schedule.tests;
    };

    const fetchReleaseDetails = async function(releaseId) {
        let res = await fetch(`/api/v1/release/${releaseId}/details`);
        if (res.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await res.json();
        if (json.status != "ok") {
            return Promise.reject(json.exception);
        }

        return json.response;
    };

    const fetchGroupDetails = async function(groupId) {
        let res = await fetch(`/api/v1/group/${groupId}/details`);
        if (res.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await res.json();
        if (json.status != "ok") {
            return Promise.reject(json.exception);
        }

        return json.response;
    };

    const fetchTestDetails = async function(testId) {
        let res = await fetch(`/api/v1/test/${testId}/details`);
        if (res.status != 200) {
            return Promise.reject("API Error");
        }
        let json = await res.json();
        if (json.status != "ok") {
            return Promise.reject(json.exception);
        }

        return json.response;
    };

    const fetchTestComment = async function (testId) {
        let params = new URLSearchParams({
            id: testId,
        });
        try {
            let response = await fetch("/api/v1/release/planner/comment/get/test?" + params);
            if (response.status == 200) {
                return response.json();
            } else {
                return Promise.reject(new Error("API Error"));
            }
        } catch (error) {
            return Promise.reject(error);
        }
    };
</script>

{#each sortByStartTime() as schedule}
    <div class="row p-2 justify-content-center">
        {#await fetchReleaseDetails(schedule.release_id)}
            <div class="col-12 text-center border rounded bg-white shadow-sm mb-2 p-2 me-2">
                <span class="spinner-border spinner-border-sm"></span> Fetching release...
            </div>
        {:then release}
            <div class="col-12 border rounded bg-white shadow-sm mb-2 p-2 me-2">
                <div class="row">
                    <div class="col-4">
                        <div>
                            <h5>Release</h5>
                                {release.name}
                        </div>
                        <div>
                            <h5>From</h5>
                            <div class="text-danger">
                                {new Date(schedule.period_start).toLocaleDateString(
                                    "en-CA"
                                )}
                            </div>
                        </div>
                        <div>
                            <h5>To</h5>
                            <div class="text-success">
                                {new Date(schedule.period_end).toLocaleDateString(
                                    "en-CA"
                                )}
                            </div>
                        </div>
                    </div>
                    <div
                        class:col-4={schedule.groups.length > 0}
                        class:col-8={schedule.groups.length == 0}
                        class:d-none={schedule.tests.length == 0}
                        class="border-start"
                    >
                        <div class:d-none={schedule.tests.length == 0}>
                            <div class="d-flex mb-2 align-items-center">
                                <div class="fw-bold fs-5">Tests</div>

                                <div class="ms-4 text-start">
                                    <a
                                        href="/workspace?{stateEncoder(prepareState(schedule))}"
                                        class="btn btn-sm btn-outline-primary"
                                    >
                                    <Fa icon={faTasks} /> To Workspace
                                    </a>
                                </div>
                            </div>
                            <div>
                                <ul class="list-group list-height-limit">
                                    {#each schedule.tests as test}
                                        <li class="list-group-item text-start">
                                            {#await fetchTestDetails(test)}
                                                <div>
                                                    <span class="spinner-border spinner-border-sm"></span> Fetching test...
                                                </div>
                                            {:then testDetails}
                                                <div class="d-flex align-items-center">
                                                    <div>
                                                            {testDetails.pretty_name || testDetails.name}
                                                    </div>
                                                    <div class="ms-auto">
                                                        {#await fetchTestComment(test)}
                                                            <span class="spinner-border spinner-border-sm"></span> Loading comment...
                                                        {:then res}
                                                            {#if res.status === "ok" && res.response}
                                                                <div class="rounded border p-1 comment-text">
                                                                    {res.response}
                                                                </div>
                                                            {/if}
                                                        {:catch error}
                                                            <div class="rounded border border-danger p-1">Error fetching comment: {error?.message ?? "Unknown"}</div>
                                                        {/await}
                                                    </div>
                                                    <div class="ms-2">
                                                        <a
                                                            target="_blank"
                                                            href={testDetails.build_system_url}
                                                            class="btn btn-sm btn-outline-dark"
                                                            >To Jenkins <Fa
                                                                icon={faExternalLinkAlt}
                                                            /></a
                                                        >
                                                    </div>
                                                </div>
                                            {/await}
                                        </li>
                                    {/each}
                                </ul>
                            </div>
                        </div>
                    </div>
                    <div
                        class:col-4={schedule.tests.length > 0}
                        class:col-8={schedule.tests.length == 0}
                        class="border-start"
                    >
                        <div class:d-none={schedule.groups.length == 0}>
                            <div class="d-flex mb-2 align-items-center">
                                <div class="fw-bold fs-5">Groups</div>
                            </div>
                            <div>
                                <ul class="list-group list-height-limit">
                                    {#each schedule.groups as group}
                                        <li class="list-group-item text-start">
                                        {#await fetchGroupDetails(group)}
                                            <div>
                                                <span class="spinner-border spinner-border-sm"></span> Fetching group...
                                            </div>
                                        {:then groupDetails}
                                            <div class="d-flex align-items-center">
                                                <div class="fs-3 fw-bold">
                                                        {groupDetails.pretty_name || groupDetails.name}
                                                </div>
                                                <div class="ms-auto">
                                                    <a
                                                        target="_blank"
                                                        href={generateJenkinsGroupUrl(groupDetails, release)}
                                                        class="btn btn-dark btn-outline"
                                                        >Jenkins <Fa
                                                            icon={faExternalLinkAlt}
                                                        /></a
                                                    >
                                                </div>
                                            </div>
                                        {/await}
                                        </li>
                                    {/each}
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        {/await}
    </div>
{/each}

<style>
    .list-height-limit {
        max-height: 256px;
        overflow-y: scroll;
    }

    .comment-text {
        font-size: 0.9em;
        max-width: 20em;
    }
</style>
