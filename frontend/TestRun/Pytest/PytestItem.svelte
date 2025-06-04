<script lang="ts">
    import {type PytestData, PytestStatus} from "./types";

    export let idx: number;
    export let testId: string;
    export let item: PytestData;

    const isFailed = () => {
        return item.status === PytestStatus.FAILURE
            || item.status === PytestStatus.FAILURE_ERROR
            || item.status === PytestStatus.ERROR
            || item.status === PytestStatus.ERROR_ERROR
            || item.status === PytestStatus.PASSED_ERROR
            || item.status === PytestStatus.XFAILED
            || item.status === PytestStatus.SKIPPED_ERROR;
    };

    const testBgColor = () => {
        if (item.status === PytestStatus.PASSED || item.status === PytestStatus.XPASS) {
            return "success";
        }

        if (isFailed()) {
            return "danger";
        }

        if (item.status === PytestStatus.SKIPPED) {
            return "warning";
        }

        return "secondary";
    };

</script>

<div class="accordion-item">
    <h2 class="accordion-header" id="headingTestCollection-{testId}-{idx}">
        <button
                class="accordion-button collapsed bg-{testBgColor()} text-white"
                type="button"
                data-bs-toggle="collapse"
                data-bs-target="#collapseTestCollection-{testId}-{idx}"
        >
            <div class="d-flex align-items-center flex-fill">
                <div class="ms-1">{item.name}</div>
            </div>
        </button>
    </h2>
    <div id="collapseTestCollection-{testId}-{idx}" class="accordion-collapse collapse">
        <div class="accordion-body">
            <table class="table">
                <thead>
                <th scope="col">Key</th>
                <th scope="col">Values</th>
                </thead>
                <tbody>
                {#each Object.entries(item) as [key, value]}
                    <tr>
                        <th scope="row">{key}</th>
                        {#if key === "markers"}
                            <td>{item.markers.join(", ")}</td>
                        {:else if key === "user_fields"}
                            <td>
                                {#each Object.entries(item.user_fields) as [key, value]}
                                    <div class="row">
                                        <div class="col-sm-4 flex-grow-1 me-auto"><strong>{key}</strong></div>
                                        <div class="col-sm-8">{value}</div>
                                    </div>
                                {/each}
                            </td>
                        {:else}
                            <td>{value}</td>
                        {/if}
                    </tr>
                {/each}
                </tbody>
            </table>
        </div>
    </div>
</div>
