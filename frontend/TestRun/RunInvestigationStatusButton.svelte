<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import { InvestigationButtonCSSClassMap, InvestigationStatusIcon, TestInvestigationStatus, TestInvestigationStatusStrings } from "../Common/TestStatus";
    import { sendMessage } from "../Stores/AlertStore";

    let { testRun } = $props();
    const dispatch = createEventDispatcher();
    let disableButtons = $state(false);

    const handleInvestigationStatus = async function (newInvestigationStatus) {
        disableButtons = true;
        try {
            let apiResponse = await fetch(
                `/api/v1/test/${testRun.test_id}/run/${testRun.id}/investigation_status/set`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        investigation_status: newInvestigationStatus,
                    }),
                }
            );
            let apiJson = await apiResponse.json();
            console.log(apiJson);
            if (apiJson.status === "ok") {
                dispatch("investigationStatusChange", { runId: testRun.id, status: newInvestigationStatus });
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error updating test run investigation status.\nMessage: ${error.response.arguments[0]}`,
                    "RunInvestigationStatusButton::handleInvestigationStatus"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test run investigation status update",
                    "RunInvestigationStatusButton::handleInvestigationStatus"
                );
            }
        } finally {
            disableButtons = false;
        }
    };
</script>

<div class="dropdown ms-2">
    <button
        class="btn {InvestigationButtonCSSClassMap[
            testRun.investigation_status
        ]} text-light"
        type="button"
        data-bs-toggle="dropdown"
    >
        <Fa
            icon={InvestigationStatusIcon[
                testRun.investigation_status
            ]}
        />
        {TestInvestigationStatusStrings[
            testRun.investigation_status
        ]}
    </button>
    <ul class="dropdown-menu">
        {#each Object.entries(TestInvestigationStatus) as [key, status]}
            <li>
                <button
                    class="dropdown-item"
                    disabled={disableButtons}
                    onclick={() => {
                        handleInvestigationStatus(status);
                    }}
                    >{TestInvestigationStatusStrings[
                        status
                    ]}</button
                >
            </li>
        {/each}
    </ul>
</div>

<style>

</style>
