<script lang="ts">
    let { nemesis_data = [] } = $props();

    const sortByFailed = function (a, b) {
        if (a.status == "failed") {
            return -1;
        } else if (b.status == "failed") {
            return 1;
        } else if (b.status == a.status) {
            return 0;
        }
    };

    const titleCase = function (string) {
        return string[0].toUpperCase() + string.slice(1).toLowerCase();
    };
</script>

<div class="container-fluid m-0 p-0">
    <div class="row m-0">
        {#each nemesis_data.sort(sortByFailed) as nemesis, idx}
            <div class="col card m-1">
                <div class="card-body">
                    <div class="card-title">
                        <h4 class="display-6">{nemesis.class_name}</h4>
                        <div class="text-monospace">{nemesis.name}</div>
                    </div>
                    <div class="card-text">
                        <span class="d-inline-block float-end">#{idx + 1}</span>
                        <ul>
                            <li>
                                <strong
                                    >Target: {nemesis.target_node.name}</strong
                                >
                            </li>
                            <li>
                                IP: {nemesis.target_node.ip}
                            </li>
                            <li>
                                Shards: {nemesis.target_node.shards}
                            </li>
                            <li>
                                Start Time: {new Date(
                                    nemesis.start_time * 1000
                                ).toISOString()}
                            </li>
                            {#if nemesis.end_time != 0}
                                <li>
                                    End Time: {new Date(
                                        nemesis.end_time * 1000
                                    ).toISOString()}
                                </li>
                                <li>
                                    Duration: {nemesis.duration}
                                </li>
                            {/if}
                            <li class="fg-nem-{nemesis.status}">
                                Status: {titleCase(nemesis.status)}
                            </li>
                            {#if nemesis.status != "succeeded" && nemesis.status != "running"}
                                <li>
                                    <pre
                                        class="font-monospace fw-6">{nemesis.stack_trace}</pre>
                                </li>
                            {/if}
                        </ul>
                    </div>
                </div>
            </div>
            {#if (idx + 1) % 2 == 0}
                <div class="w-100"></div>
            {/if}
        {:else}
            <div class="row">
                <div class="col text-center p-1 text-muted">
                    No nemeses submitted.
                </div>
            </div>
        {/each}
    </div>
</div>

<style>
    .fg-nem-succeeded {
        color: rgb(70, 187, 70);
    }

    .fg-nem-skipped {
        color: rgb(218, 108, 36);
    }

    .fg-nem-failed {
        color: rgb(163, 31, 31);
    }

    .test-status-fg-running {
        color: rgb(221, 221, 50);
    }

    .test-status-bg-passed {
        color: white;
        background-color: rgb(37, 143, 37);
        border-color: rgb(37, 143, 37);
    }

    .test-status-bg-running {
        color: white;
        background-color: rgb(221, 221, 50);
        border-color: rgb(221, 221, 50);
    }

    .test-status-bg-failed {
        color: white;
        background-color: rgb(185, 23, 23);
        border-color: rgb(185, 23, 23);
    }

    .cursor-question {
        cursor: help;
    }
</style>
