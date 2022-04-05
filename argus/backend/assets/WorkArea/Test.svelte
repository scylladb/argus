<script>
    import { createEventDispatcher } from "svelte";
    import { stats } from "../Stores/StatsSubscriber";
    import { StatusBackgroundCSSClassMap } from "../Common/TestStatus.js";
    import { timestampToISODate } from "../Common/DateUtils";
    import AssigneeList from "./AssigneeList.svelte";
    export let release = "";
    export let group = "";
    export let filtered = false;
    export let test = {
        assignee: [],
        description: null,
        group_id: null,
        id: null,
        name: "ERROR",
        pretty_name: null,
        release_id: null,
        build_system_id: "",
    };
    export let lastStatus = "unknown";
    export let runs = {};
    export let assigneeList = [];
    const dispatch = createEventDispatcher();
    let startTime;
    let fetching = false;
    $: lastStatus = $stats?.["releases"]?.[release]?.["groups"]?.[group]?.["tests"]?.[test.name]["status"] ?? lastStatus;
    $: startTime = $stats?.["releases"]?.[release]?.["groups"]?.[group]?.["tests"]?.[test.name]["start_time"] ?? startTime;

    const titleCase = function (string) {
        return string[0].toUpperCase() + string.slice(1).toLowerCase();
    };


    const handleTestClick = function (e) {
        if (runs[`${release}/${group}/${test.name}`]) {
            dispatch("testRunRemove", { runId: `${release}/${group}/${test.name}`});
            return;
        }
        if (fetching) return;
        fetching = true;
        dispatch("testRunRequest", {
            uuid: `${release}/${group}/${test.name}`,
            key: test.build_system_id,
            test: test.name,
            group: group,
            release: release
        });
        fetching = false;
    };
</script>

<li
    class:d-none={filtered}
    class:active={runs[`${release}/${group}/${test.name}`]}
    class:active-test-text={runs[`${release}/${group}/${test.name}`]}
    class="list-group-item argus-test"
    on:click={handleTestClick}
>
    <div class="container-fluid p-0 m-0">
        <div class="row p-0 m-0 align-items-center">
            <div class="col-1 text-center">
                {#if lastStatus}
                    <span
                        title={titleCase(lastStatus)}
                        class="cursor-question status-circle {StatusBackgroundCSSClassMap[lastStatus] ?? StatusBackgroundCSSClassMap["unknown"]}"
                        ></span
                    >
                {/if}
            </div>
            <div class="col-10 overflow-hidden">
                <div class="d-flex">
                    <div>{test.pretty_name || test.name}</div>
                    <div class="ms-auto text-right">
                        <AssigneeList assignees={assigneeList}/>
                    </div>
                </div>
                {#if startTime}
                <div
                    class:text-muted={!runs[`${release}/${test.name}`]}
                    class:active-test-text-muted={runs[`${release}/${test.name}`]}
                    style="font-size: 0.75em"
                >
                    {timestampToISODate(startTime)}
                </div>
                {/if}
            </div>
            <div class="col-1 text-center">
                {#if fetching}
                    <span class="spinner-border spinner-border-sm text-dark" />
                {/if}
            </div>
        </div>
    </div>
</li>

<style>
    .active-test-text {
        color: black;
    }

    .active-test-text-muted {
        color: rgb(54, 54, 54);
    }

    .argus-test {
        cursor: pointer;
    }

    .status-circle {
        display: inline-block;
        padding: 8px;
        border-radius: 50%;
    }

    .cursor-question {
        cursor: help;
    }

    .argus-test-loading {
        background-color: orange;
    }

    .text-success {
        color: #54be54;
    }

    .text-failed {
        color: #bb2b2b;
    }

    .test-passed {
        color: #54be54;
    }

    .test-running {
        color: #d6c52e;
    }
    .test-failed {
        color: #bb2b2b;
    }
    .test-unknown {
        color: #e9e6c4;
    }

    .test-none {
        color: #b1b1b1;
    }

    .test-created {
        color: #2ebcf5;
    }

    .text-running {
        color: #ebe841;
    }
</style>
