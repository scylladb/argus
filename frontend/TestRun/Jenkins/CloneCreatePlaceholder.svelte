<script>
    import { createEventDispatcher, onMount } from "svelte";
    import { sendMessage } from "../../Stores/AlertStore";

    /**
     * @type {{
     * currentTestId: string,
     * newName: string,
     * target: string,
     * group: string,
     * advancedSettings: boolean | { [string]: string },
     * }} args
     */
    export let args;
    const dispatch = createEventDispatcher();

    let result;

    const cloneJob = async function() {
        try {
            const response = await fetch("/api/v1/jenkins/clone/create", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(args),
            });

            const json = await response.json();
            if (json.status != "ok") {
                throw json;
            }

            console.log(json.response);
            result = json.response;

        } catch (error) {
            if (error?.status === "error") {
                sendMessage(
                    "error",
                    `API Error during job clone.\nMessage: ${error.response.arguments[0]}`
                );
            } else {
                sendMessage(
                    "error",
                    "A backend error occurred during job clone"
                );
                console.log(error);
            }
        }
    };

    onMount(async () => {
        cloneJob();
    });
</script>

<div>
    {#if result}
        <div class="mb-6">
            <h6>Clone successful!</h6>
            <div>
                Created <a href="{result.new_job.url}">{result.new_entity.build_system_id}</a>.
            </div>
        </div>
        <div>
            <button class="btn btn-success w-100" on:click={() => {
                dispatch("exit", {
                    newBuildId: result.new_entity.build_system_id
                });
            }}>Next</button>
        </div>
    {:else}
        <span class="spinner-border spinner-border-sm"></span> Cloning...
    {/if}
</div>