<script>
    import Fa from "svelte-fa";
    import { StatusCSSClassMap } from "../Common/TestStatus";
    import { timestampToISODate } from "../Common/DateUtils";
    import { createEventDispatcher } from "svelte";
    import { stateEncoder } from "../Common/StateManagement";
    import { assigneeStore } from "../Stores/AssigneeSubscriber";
    import AssigneeList from "../WorkArea/AssigneeList.svelte";
    import {
        faCircle,
        faTimes,
        faAngleDoubleDown,
        faBug,
        faHammer,
        faExternalLinkSquareAlt,
    } from "@fortawesome/free-solid-svg-icons";
    import { faGithub } from "@fortawesome/free-brands-svg-icons";
    export let tests = {};
    export let releaseName = "";
    let encodedState = "state=e30";
    $: encodedState = stateEncoder(
        Object.values(tests).reduce((acc, val) => {
            acc[`${releaseName}/${val.group}/${val.name}`] = {
                test: val.name,
                group: val.group,
                release: releaseName,
                build_system_id: val.build_system_id
            };
            return acc;
        }, {})
    );
    let assigneeList = {};
    $: assigneeList = $assigneeStore?.[releaseName] ?? {
        groups: {},
        tests: {},
    };
    const dispatch = createEventDispatcher();
    const handleTrashClick = function (name, group) {
        dispatch("deleteRequest", {
            name: name,
            group: group,
        });
    };

    const getAssigneesForTest = function (test) {
        let testAssignees =
            assigneeList.tests?.[`${test.group}/${test.name}`] ?? [];
        let groupAssignees = assigneeList.groups?.[test.group] ?? [];
        return [...testAssignees, ...groupAssignees];
    };
</script>

<div class="sticky">
    {#if Object.values(tests).length > 0}
        <div class="d-flex flex-column">
            <ul class="list-group popout-tests">
                {#each Object.values(tests) as test (test.name)}
                    <li class="list-group-item">
                        <div class="d-flex align-items-center">
                            <div class="d-flex">
                                <div>
                                    {#if assigneeList}
                                        <AssigneeList
                                            assignees={getAssigneesForTest(
                                                test
                                            )}
                                        />
                                    {/if}
                                </div>
                                <span class="ms-2 fw-bold"
                                    >{test.group}/{test.name}</span
                                >
                            </div>
                            <button
                                class="ms-auto btn btn-secondary btn-sm"
                                data-bs-toggle="collapse"
                                data-bs-target="#collapse-builds-{test.name}"
                                title="Latest builds"
                                ><Fa icon={faAngleDoubleDown} /></button
                            >
                            <button
                                class="ms-1 btn btn-secondary btn-sm"
                                title="Dismiss"
                                on:click={() => handleTrashClick(test.name, test.group)}
                                ><Fa icon={faTimes} /></button
                            >
                        </div>
                        <div
                            class="collapse show"
                            id="collapse-builds-{test.name}"
                        >
                            <ul class="list-unstyled">
                                {#each test.last_runs as run, idx}
                                    <li class="my-1" class:border-top={idx > 0}>
                                        <div class="d-flex align-items-center">
                                            <div
                                                class="ms-2 {StatusCSSClassMap[
                                                    run.status
                                                ]}"
                                            >
                                                <Fa icon={faCircle} />
                                            </div>
                                            <div class="ms-2">
                                                <a
                                                    target="_blank"
                                                    href={run.build_job_url}
                                                    class="link-dark"
                                                >
                                                    #{run.build_number}
                                                </a>
                                            </div>
                                            <div class="ms-auto me-1">
                                                {#if run.assignee}
                                                    <AssigneeList
                                                        assignees={[
                                                            run.assignee,
                                                        ]}
                                                        smallImage={true}
                                                    />
                                                {/if}
                                            </div>
                                            <div class="text-muted small-text">
                                                {timestampToISODate(
                                                    run.start_time * 1000
                                                )}
                                            </div>
                                        </div>
                                        <div>
                                            <ul class="list-unstyled">
                                                {#each run.issues as issue}
                                                    <li
                                                        class="ms-3 d-flex align-items-center"
                                                    >
                                                        <div class="ms-1">
                                                            <Fa
                                                                icon={faGithub}
                                                            />
                                                        </div>
                                                        <div class="ms-1">
                                                            <a
                                                                target="_blank"
                                                                href={issue.url}
                                                            >
                                                                {issue.title}
                                                            </a>
                                                        </div>
                                                        <div
                                                            class="ms-auto text-muted"
                                                        >
                                                            {issue.owner}/{issue.repo}#{issue.issue_number}
                                                        </div>
                                                    </li>
                                                {/each}
                                            </ul>
                                        </div>
                                    </li>
                                {/each}
                            </ul>
                        </div>
                    </li>
                {/each}
            </ul>
            <a
                href="/run_dashboard?{encodedState}"
                class="btn btn-primary"
                target="_blank"
                >Investigate selected <Fa icon={faExternalLinkSquareAlt} /></a
            >
        </div>
    {/if}
</div>

<style>
    .small-text {
        font-size: 0.75em;
    }

    .sticky {
        position: sticky;
        top: 1em;
    }

    .popout-tests {
        height: 1100px;
        overflow-y: scroll;
    }

    @media screen and (max-height: 1080px) {
        .popout-tests {
            height: 900px;
        }
    }

    @media screen and (max-height: 720px) {
        .popout-tests {
            height: 500px;
        }
    }

    @media screen and (max-height: 480px) {
        .popout-tests {
            height: 320px;
        }

    }

    @media screen and (max-height: 320px) {

        .popout-tests {
            height: 200px;
        }
    }
</style>
