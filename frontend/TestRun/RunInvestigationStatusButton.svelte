<script>
    import { faEye, faEyeSlash, faSearch } from "@fortawesome/free-solid-svg-icons";
    import { createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";
    import { InvestigationButtonCSSClassMap, TestInvestigationStatus, TestInvestigationStatusStrings } from "../Common/TestStatus";
    import { sendMessage } from "../Stores/AlertStore";

    export let testRun;
    const dispatch = createEventDispatcher();
    let disableButtons = false;

    const investigationStatusIcon = {
        in_progress: faSearch,
        not_investigated: faEyeSlash,
        investigated: faEye,
    };

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
                dispatch("statusUpdate", { status: newInvestigationStatus });
            } else {
                throw apiJson;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error updating test run investigation status.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test run investigation status update"
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
            icon={investigationStatusIcon[
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
                    on:click={() => {
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
