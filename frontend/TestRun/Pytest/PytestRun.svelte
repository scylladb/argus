<script lang="ts">
    import {onMount, onDestroy} from "svelte";
    import {sendMessage} from "../../Stores/AlertStore";

    const enum PytestStatus {
        ERROR = "error",
        PASSED = "passed",
        FAILURE = "failure",
        SKIPPED = "skipped",
        XFAILED = "xfailed",
        XPASS = "xpass",
        PASSED_ERROR = "passed & error",
        FAILURE_ERROR = "failure & error",
        SKIPPED_ERROR = "skipped & error",
        ERROR_ERROR = "error & error",
    }

    type PytestData = {
        name: string,
        timestamp: number,
        session_timestamp: number,
        test_type: string,
        run_id: string,
        status: PytestStatus,
        duration: number,
        markers: string[],
        user_fields: { [key: string]: string },
    };

    export let testRunId: string;

    let data: PytestData[] | null = null;
    let refreshInterval: any = null;
    let failedToLoad = false;

    const fetchData = async () => {
        try {
            const response = await fetch(`/api/v1/run/${testRunId}/pytest/results`);
            const responseData: { status: string, response: PytestData[] } = await response.json();

            if (!response.ok) {
                failedToLoad = true;
                sendMessage(
                    "error",
                    "API Error when fetching test run data.",
                    "DriverMatrixTestRun::fetchTestRunData"
                );
                return null;
            }

            return responseData.response;
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching test run data.\nMessage: ${error.response.arguments[0]}`,
                    "DriverMatrixTestRun::fetchTestRunData"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test run data fetch",
                    "DriverMatrixTestRun::fetchTestRunData"
                );
            }
        }

        return null;
    };

    onMount(async () => {
        data = await fetchData();
        if (data) {
            refreshInterval = setInterval(async () => {
                const newData = await fetchData();
                if (newData) {
                    data = newData;
                }
            }, 5000);
        }
    });

    onDestroy(() => clearInterval(refreshInterval));

</script>

{#if data}
    <div
            class="tab-pane fade"
            id="nav-pytest-{testRunId}"
            role="tabpanel"
    ></div>
{:else if failedToLoad}
<div class="text-center p-2 m-1 d-flex align-items-center justify-content-center">
    <span class="fs-4">Run not found.</span>
</div>
{:else}
<div class="text-center p-2 m-1 d-flex align-items-center justify-content-center">
    <span class="spinner-border me-4" /><span class="fs-4">Loading...</span>
</div>
{/if}
