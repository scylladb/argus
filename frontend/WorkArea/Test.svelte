<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import { StatusBackgroundCSSClassMap } from "../Common/TestStatus.js";
    import { timestampToISODate } from "../Common/DateUtils";
    import AssigneeList from "./AssigneeList.svelte";
    interface Props {
        filtered?: boolean;
        test?: any;
        testStats: any;
        runs?: any;
        assigneeList?: any;
    }

    let {
        filtered = false,
        test = {
        assignee: [],
        description: null,
        group_id: null,
        name: "ERROR",
        pretty_name: null,
        release_id: null,
        id: "",
    },
        testStats,
        runs = [],
        assigneeList = []
    }: Props = $props();
    const dispatch = createEventDispatcher();
    let fetching = $state(false);

    const titleCase = function (string) {
        return string[0].toUpperCase() + string.slice(1).toLowerCase();
    };


    const handleTestClick = function (e) {
        if (runs.find(v => v == test.id)) {
            dispatch("testRunRemove", { testId: test.id });
            return;
        }
        if (fetching) return;
        fetching = true;
        dispatch("testRunRequest", {
            testId: test.id
        });
        fetching = false;
    };
</script>

<li
    class:d-none={filtered}
    class:active={runs.find(v => v == test.id)}
    class:active-test-text={runs.find(v => v == test.id)}
    class="list-group-item argus-test"
    onclick={handleTestClick}
>
    <div class="container-fluid p-0 m-0">
        <div class="row p-0 m-0 align-items-center">
            <div class="col-1 text-center">
                {#if testStats?.status}
                    <span
                        title={titleCase(testStats?.status ?? "unknown")}
                        class="cursor-question status-circle {StatusBackgroundCSSClassMap[testStats?.status] ?? StatusBackgroundCSSClassMap["unknown"]}"
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
                {#if testStats?.start_time}
                <div
                    class:text-muted={!runs.find(v => v == test.id)}
                    class:active-test-text-muted={runs.find(v => v == test.id)}
                    style="font-size: 0.75em"
                >
                    {timestampToISODate(testStats.start_time)}
                </div>
                {/if}
            </div>
            <div class="col-1 text-center">
                {#if fetching}
                    <span class="spinner-border spinner-border-sm text-dark"></span>
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
