<script lang="ts">
    import { run as run_1 } from 'svelte/legacy';

    import Fa from "svelte-fa";
    import { StatusCSSClassMap } from "../Common/TestStatus";
    import { timestampToISODate } from "../Common/DateUtils";
    import { createEventDispatcher } from "svelte";
    import { stateEncoder } from "../Common/StateManagement";
    import AssigneeList from "../WorkArea/AssigneeList.svelte";
    import {
        faCircle,
        faTimes,
        faAngleDoubleDown,
        faBug,
        faExternalLinkSquareAlt,
        faTrash,
        faComment,
        faArrowUp,
    } from "@fortawesome/free-solid-svg-icons";
    import { faGithub } from "@fortawesome/free-brands-svg-icons";
    interface Props {
        tests?: any;
        releaseName?: string;
    }

    let { tests = $bindable({}), releaseName = "" }: Props = $props();
    let encodedState = $state("e30");
    let top = $state();
    let sticky = $state(false);
    let observer = new IntersectionObserver((entries) => {
        let entry = entries[0];
        if (!entry) return;
        if (entry.intersectionRatio == 0 && !entry.isIntersecting) {
            sticky = true;
        } else {
            sticky = false;
        }
    }, {
        threshold: [0, 0.25, 0.5, 0.75, 1]
    });

    run_1(() => {
        encodedState = stateEncoder(
            Object.values(tests).map(v => v.id)
        );
    });

    const dispatch = createEventDispatcher();
    const handleTrashClick = function (id) {
        dispatch("deleteRequest", {
            id: id
        });
    };

    run_1(() => {
        top ? observer.observe(top) : observer.disconnect();
    });

</script>

<div class="position-fixed" style="top: 95%; left: 98%" class:d-none={!sticky}>
    <button class="btn btn-primary" onclick={() => window.scrollTo({behavior: "smooth", top: 0 })}><Fa icon={faArrowUp}/></button>
</div>
<div class="">
    <div bind:this={top}></div>
    {#if Object.values(tests).length > 0}
        <div class="d-flex flex-column">
            <div class:sticky={sticky}>
                <div class="d-flex align-items center mb-2">
                    <a
                        href="/workspace?state={encodedState}"
                        class="btn btn-primary w-75 me-1"
                        >Investigate selected <Fa icon={faExternalLinkSquareAlt} /></a
                    >
                    <button
                        class="btn btn-danger w-25"
                        onclick={() => tests = {}}
                        ><Fa icon={faTrash} /> Remove All</button
                    >
                </div>
            </div>
            <ul class="list-group">
                {#each Object.values(tests) as test (test.id)}
                    <li class="list-group-item">
                        <div class="d-flex align-items-center">
                            <div class="d-flex">
                                <div>
                                    {#if test.assignees}
                                        <AssigneeList
                                            assignees={test.assignees}
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
                                onclick={() => handleTrashClick(test.id)}
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
                                                    href="/test/{test.id}/runs?additionalRuns[]={run.id}"
                                                    class="link-dark"
                                                >
                                                    #{run.build_number}
                                                </a>
                                            </div>
                                            <div class="ms-auto"></div>
                                            {#if run.issues.length > 0}
                                                <div class="ms-2" title="Has Issues">
                                                    <Fa icon={faBug} />
                                                </div>
                                            {/if}
                                            {#if run.comments.length > 0}
                                                <div class="ms-2" title="Has Comments">
                                                    <Fa icon={faComment} />
                                                </div>
                                            {/if}
                                            {#if run.assignee}
                                                <div class="ms-2">
                                                    <AssigneeList
                                                        assignees={[
                                                            run.assignee,
                                                        ]}
                                                        smallImage={true}
                                                    />
                                                </div>
                                            {/if}
                                            <div class="ms-2 text-muted small-text">
                                                {timestampToISODate(
                                                    run.start_time
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
                                                            {issue.owner}/{issue.repo}#{issue.number}
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
            <div style="height: 8em"></div>
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
        z-index: 10;
    }

</style>
