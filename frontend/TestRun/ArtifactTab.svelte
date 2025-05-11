<script>
    import { faPlus } from "@fortawesome/free-solid-svg-icons";
    import ArtifactRow from "./ArtifactRow.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";

    export let testRun;
    export let testInfo;

    let logName = "";
    let logLink = "";
    const dispatch = createEventDispatcher();

    const addLogLink = async function() {
        try {
            let res = await fetch(`/api/v1/client/testrun/scylla-cluster-tests/${testRun.id}/logs/submit`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    logs: [
                        {
                            "log_name": logName,
                            "log_link": logLink,
                        }
                    ]
                })
            });

            let result = await res.json();
            if (result.status === "ok") {
                sendMessage("success", "Log link added to run!", "ArtifactTab::addLogLink");
                dispatch("refreshRequest");
            } else {
                throw result;
            }
        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error when fetching test run data.\nMessage: ${error.response.arguments[0]}`,
                    "ArtifactTab::addLogLink"
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during test run data fetch",
                    "ArtifactTab::addLogLink"
                );
                console.log(error);
            }
        }
    };
</script>

<div>
    <div class="p-2 mb-2">
        <button
            class="btn btn-success"
            data-bs-toggle="collapse"
            data-bs-target="#collapseAddLink-{testRun.id}"
        >
            <Fa icon={faPlus}/>
            Add Log Link
        </button>
    </div>
    <div class="m-2 collapse border rounded p-2" id="collapseAddLink-{testRun.id}">
        <div class="mb-2">
            <label class="form-label">Log Name</label>
            <input class="form-control" type="text" placeholder="Friendly Log Name" bind:value={logName}>
        </div>
        <div class="mb-2">
            <label class="form-label">Log URL</label>
            <input class="form-control" type="text" placeholder="URL for the Log File" bind:value={logLink}>
        </div>
        <div>
            <button
                class="btn btn-sm btn-primary"
                data-bs-toggle="collapse"
                data-bs-target="#collapseAddLink-{testRun.id}"
                on:click={addLogLink}>
                Submit
            </button>
        </div>
    </div>
</div>

{#if testRun.logs.length > 0}
<table
    class="table table-bordered table-sm text-center"
>
    <thead>
        <th>Log Type</th>
        <th>Log URL</th>
    </thead>
    <tbody>
        {#each testRun.logs as [name, link], idx}
            <ArtifactRow artifactName={name} originalLink={link} artifactLink={`/api/v1/tests/${testInfo.test.plugin_name}/${testRun.id}/log/${name}/download`}/>
        {/each}
    </tbody>
</table>
{:else}
<div class="row">
    <div class="col text-center p-1 text-muted">
        No logs.
    </div>
</div>
{/if}
