<script>
    import Fa from "svelte-fa";
    import {
        faCircle,
        faTrashAlt,
        faExternalLinkSquareAlt,
    } from "@fortawesome/free-solid-svg-icons";
    import { StatusCSSClassMap } from "./TestStatus";
    import { createEventDispatcher } from "svelte";
    import { Base64 } from "js-base64";
    export let scheduleData = {};
    export let releaseData = {};
    export let releaseStats = {};
    export let users = {};
    const dispatch = createEventDispatcher();
    let state = "e30";
    $: makeState();
    const getPicture = function (id) {
        return id ? `/storage/picture/${id}` : "/static/no-user-picture.png";
    };

    const handleScheduleDelete = function () {
        dispatch("deleteSchedule", {
            id: scheduleData.schedule_id,
        });
    };

    const makeState = function () {
        let tests = releaseStats.tests ?? [];
        if (tests.length == 0) {
            state = "e30";
        }

        let testsForGroups = scheduleData.groups
            .map((group) => {
                return Object.keys(tests).filter((test) =>
                    new RegExp(group).test(test)
                );
            })
            .reduce((acc, val) => {
                return [acc, ...val];
            }, []);
        let combinedTests = [...scheduleData.tests, ...testsForGroups];
        let uniqueTestsWithStatus = combinedTests
            .reduce((acc, test) => {
                if (
                    (releaseStats?.tests[test]?.status ?? "unknown") !=
                        "unknown" &&
                    acc.findIndex((val) => val == test) == -1
                ) {
                    acc.push(test);
                }
                return acc;
            }, [])
            .sort();
        let rawState = uniqueTestsWithStatus.reduce((acc, val) => {
            acc[`${releaseData.release.name}/${val}`] = {
                release: releaseData.release.name,
                test: val,
                runs: [],
            };
            return acc;
        }, {});
        state = Base64.encode(JSON.stringify(rawState), true);
    };
</script>

<div class="row">
    <div class="col">
        <div
            class="border rounded shadow-sm mb-3 p-3 d-flex align-items-start justify-content-center"
        >
            <div
                class="me-3"
                class:w-25={scheduleData.tests.length > 0}
                class:w-50={scheduleData.tests.length == 0}
                class:d-none={scheduleData.groups.length == 0}
            >
                <h6>Groups</h6>
                <ul class="list-group">
                    {#each scheduleData.groups as group}
                        <li class="list-group-item d-flex align-items-center">
                            <div
                                class="{StatusCSSClassMap[
                                    releaseStats?.groups[group]?.lastStatus
                                ]} cursor-question me-2"
                                title={releaseStats?.groups[group]?.lastStatus}
                            >
                                <Fa icon={faCircle} />
                            </div>
                            <div>
                                {releaseData.groups.find(
                                    (val) => val.name == group
                                ).pretty_name}
                            </div>
                        </li>
                    {/each}
                </ul>
            </div>
            <div
                class="me-3"
                class:w-25={scheduleData.groups.length > 0}
                class:w-50={scheduleData.groups.length == 0}
                class:d-none={scheduleData.tests.length == 0}
            >
                <h6>Tests</h6>
                <ul class="list-group">
                    {#each scheduleData.tests as test}
                        <li class="list-group-item d-flex align-items-center">
                            <div
                                class="{StatusCSSClassMap[
                                    releaseStats?.tests[test]?.status
                                ]} cursor-question me-2"
                                title={releaseStats?.tests[test]?.status}
                            >
                                <Fa icon={faCircle} />
                            </div>
                            <div>{test}</div>
                        </li>
                    {/each}
                </ul>
            </div>
            <div class="me-3 w-25">
                <h6>Date</h6>
                <div>
                    From:
                    <div class="text-muted font-small">
                        {new Date(
                            scheduleData.period_start
                        ).toLocaleDateString()}
                    </div>
                </div>
                <div>
                    To:
                    <div class="text-muted font-small">
                        {new Date(scheduleData.period_end).toLocaleDateString()}
                    </div>
                </div>
            </div>
            <div class="me-3 w-25">
                <h6>Assignees</h6>
                <ul class="list-group mb-3">
                    {#each scheduleData.assignees as assignee}
                        <li class="list-group-item d-flex align-items-center">
                            <div class="me-2">
                                <img
                                    class="img-profile"
                                    src={getPicture(
                                        users[assignee]?.picture_id
                                    )}
                                    alt=""
                                />
                            </div>
                            <div>{users[assignee]?.username}</div>
                        </li>
                    {/each}
                </ul>
                <div class="text-end">
                    <a
                        class="btn btn-primary"
                        href="/run_dashboard?state={state}"
                        target="_blank"
                    >
                        <Fa icon={faExternalLinkSquareAlt} />
                    </a>
                    <button
                        class="btn btn-danger"
                        on:click={handleScheduleDelete}
                    >
                        <Fa icon={faTrashAlt} />
                    </button>
                </div>
            </div>
        </div>
    </div>
</div>

<style>
    .font-small {
        font-size: 0.9em;
    }
    .img-profile {
        height: 32px;
        border-radius: 50%;
        object-fit: cover;
    }

    .cursor-question {
        cursor: help;
    }
</style>
