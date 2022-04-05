<script>
    export let schedules = [];
    import Fa from "svelte-fa";
    import {
        faExternalLinkAlt,
        faTasks,
    } from "@fortawesome/free-solid-svg-icons";
    import { allTests, allGroups, allReleases} from "../Stores/WorkspaceStore";
    import { stateEncoder } from "../Common/StateManagement";

    let releases = {};
    let groups = {};
    let tests = {};

    allReleases.subscribe((value) => {
        if (!value) return;
        releases = value.reduce((acc, val) => {
            acc[val.id] = val;
            return acc;
        }, {});
    });

    allGroups.subscribe((value) => {
        if (!value) return;
        groups = value.reduce((acc, val) => {
            acc[val.id] = val;
            return acc;
        }, {});
    });

    allTests.subscribe((value) => {
        if (!value) return;
        tests = value.reduce((acc, val) => {
            acc[val.id] = val;
            return acc;
        }, {});
    });

    const generateJenkinsUrl = function(id, type = "test") {
        // TODO: Store URLs in entities
        if (!id) return "";
        const baseURL = "https://jenkins.scylladb.com/";
        switch (type) {
            case "test": {
                let test = tests?.[id];
                let group = groups?.[test.group_id];
                let release = releases?.[test.release_id];
                return `${baseURL}job/${release?.name}/job/${group?.name}/job/${test?.name}`;
            }
            case "group": {
                let group = groups?.[id];
                let release = releases?.[group.release_id];
                return `${baseURL}job/${release?.name}/job/${group?.name}`;
            }
        }
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

    const prepareState = function (schedule, releases, groups, tests) {
        return schedule.tests.reduce((acc, scheduledTest) => {
            let testId = scheduledTest;
            let releaseId = schedule.release_id;
            let groupId = tests?.[testId]?.group_id;
            let releaseName = releases?.[releaseId]?.name;
            let groupName = groups?.[groupId]?.name;
            let testName = tests?.[testId]?.name;
            let buildSystemId = tests?.[testId]?.build_system_id;
            acc[`${releaseName}/${groupName}/${testName}`] = {
                release: releaseName,
                group: groupName,
                test: testName,
                build_system_id: buildSystemId,
            };
            return acc;
        }, {});
    };
</script>

{#each sortByStartTime() as schedule}
    <div class="row p-2 justify-content-center">
        <div class="col-12 border rounded bg-white shadow-sm mb-2 p-2 me-2">
            <div class="row">
                <div class="col-4">
                    <div>
                        <h5>Release</h5>
                        <div>{releases?.[schedule.release_id]?.name}</div>
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
                                    href="/workspace?{stateEncoder(
                                        prepareState(
                                            schedule,
                                            releases,
                                            groups,
                                            tests
                                        )
                                    )}"
                                    class="btn btn-sm btn-outline-primary"
                                >
                                    Open Workspace <Fa icon={faTasks} />
                                </a>
                            </div>
                        </div>
                        <div>
                            <ul class="list-group list-height-limit">
                                {#each schedule.tests as test}
                                    <li class="list-group-item text-start">
                                        <div class="d-flex align-items-center">
                                            <div>
                                                {tests?.[test]?.pretty_name ||
                                                    tests?.[test]?.name}
                                            </div>
                                            <div class="ms-auto">
                                                <a
                                                    target="_blank"
                                                    href={tests?.[test]?.build_system_url}
                                                    class="btn btn-sm btn-outline-dark"
                                                    >To Jenkins <Fa
                                                        icon={faExternalLinkAlt}
                                                    /></a
                                                >
                                            </div>
                                        </div>
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
                                        <div class="d-flex align-items-center">
                                            <div class="fs-3 fw-bold">
                                                {groups?.[group]?.pretty_name ||
                                                    groups?.[group]?.name}
                                            </div>
                                            <div class="ms-auto">
                                                <a
                                                    target="_blank"
                                                    href={generateJenkinsUrl(groups?.[group]?.id, "group")}
                                                    class="btn btn-dark btn-outline"
                                                    >Jenkins <Fa
                                                        icon={faExternalLinkAlt}
                                                    /></a
                                                >
                                            </div>
                                        </div>
                                    </li>
                                {/each}
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
{/each}

<style>
    .list-height-limit {
        max-height: 256px;
        overflow-y: scroll;
    }
</style>
