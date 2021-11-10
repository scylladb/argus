<script>
    import { createEventDispatcher } from "svelte";
    import { testRequests, stats } from "./StatsSubscriber";

    export let release = "";
    export let group = "";
    export let test = {
        assignee: [],
        description: null,
        group_id: null,
        id: null,
        name: "ERROR",
        pretty_name: null,
        release_id: null,
    };
    export let lastStatus = "unknown";
    let runs_uuid = crypto.randomUUID();
    let fetching = false;
    let runs = [];
    let listItem;
    testRequests.update((val) => [...val, [release, group, test.name]]);
    stats.subscribe((val) => {
        lastStatus =
            val["tests"]?.[release]?.[group]?.[test.name]["lastStatus"] ??
            lastStatus;
    });
    const removeDots = function (str) {
        return str.replaceAll(".", "_");
    };

    const titleCase = function (string) {
        return string[0].toUpperCase() + string.slice(1).toLowerCase();
    };

    const dispatch = createEventDispatcher();

    const fetchTestRuns = function (e) {
        if (fetching) return;
        listItem.classList.add("active");
        fetching = true;
        fetch("/api/v1/test_runs", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                release: release,
                group: group,
                test_name: test.name,
            }),
        })
            .then((res) => {
                if (res.status == 200) {
                    return res.json();
                } else {
                    console.log("Error during test_run fetch");
                }
            })
            .then((res) => {
                if (res.status == "ok") {
                    runs = res.response;
                    dispatch("testRunRequest", {
                        uuid: runs_uuid,
                        runs: runs,
                        test: test,
                        release: release
                    });
                    lastStatus = runs[0].status;
                    console.log(res.response);
                } else {
                    console.log("Error parsing test_run data");
                    console.log(res.response);
                }
                fetching = false;
            });
    };
</script>

<li
    bind:this={listItem}
    class="list-group-item argus-test"
    on:click={fetchTestRuns}
>
    <div class="container-fluid p-0 m-0">
        <div class="row p-0 m-0">
            <div class="col-1 text-center">
                {#if lastStatus}
                    <span
                        title={titleCase(lastStatus)}
                        class="cursor-question test-{lastStatus}"
                        ><i class="fas fa-circle" /></span
                    >
                {/if}
            </div>
            <div class="col-10 overflow-hidden">
                {test.pretty_name ?? test.name}
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
    .argus-test {
        cursor: pointer;
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
