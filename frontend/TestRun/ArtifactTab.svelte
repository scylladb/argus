<script lang="ts">
    import { faPlus, faDownload } from "@fortawesome/free-solid-svg-icons";
    import ArtifactRow from "./ArtifactRow.svelte";
    import { sendMessage } from "../Stores/AlertStore";
    import { createEventDispatcher } from "svelte";
    import Fa from "svelte-fa";

    let { testRun, testInfo } = $props();

    let logName = $state("");
    let logLink = $state("");
    const dispatch = createEventDispatcher();
    const DOWNLOAD_DELAY_MS = 800

    const getArtifactDownloadLink = (logName: string) =>
        `/api/v1/tests/${testInfo.test.plugin_name}/${testRun.id}/log/${logName}/download`;

    const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

    const downloadAllArtifacts = async () => {
        if (!testRun?.logs?.length) return;
        if (typeof document === "undefined") return;

        for (const [logName] of testRun.logs) {
            const downloadUrl = getArtifactDownloadLink(logName);
            const linkElement = document.createElement("a");
            linkElement.href = downloadUrl;
            linkElement.setAttribute("download", "");
            linkElement.style.display = "none";
            document.body.appendChild(linkElement);
            linkElement.click();
            document.body.removeChild(linkElement);

            await delay(DOWNLOAD_DELAY_MS);
        }
    };

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
    <div class="p-2 mb-2 d-flex gap-2 flex-wrap">
        <button
            class="btn btn-success"
            type="button"
            data-bs-toggle="collapse"
            data-bs-target="#collapseAddLink-{testRun.id}"
        >
            <Fa icon={faPlus}/>
            Add Log Link
        </button>
        {#if testRun.logs.length > 0}
            <button
                class="btn btn-outline-primary ms-auto"
                type="button"
                onclick={downloadAllArtifacts}
            >
                <Fa icon={faDownload}/>
                Download All
            </button>
        {/if}
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
                onclick={addLogLink}>
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
        <tr>
            <th>Log Type</th>
            <th>Log URL</th>
        </tr>
    </thead>
    <tbody>
        {#each testRun.logs as [name, link], idx}
            <ArtifactRow artifactName={name} originalLink={link} artifactLink={getArtifactDownloadLink(name)}/>
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
