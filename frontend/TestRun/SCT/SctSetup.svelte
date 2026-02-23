<script lang="ts">
    import Fa from "svelte-fa";
    import type { SCTTestRun, StressCommand } from "../TestRun.svelte";
    import { faAngleDown, faAngleUp, faCopy } from "@fortawesome/free-solid-svg-icons";
    import { timestampToISODate } from "../../Common/DateUtils";
    import { sendMessage } from "../../Stores/AlertStore";
    import { onMount } from "svelte";

    let {
        testRun
    }: { testRun: SCTTestRun} = $props();

    let stressCommands: StressCommand[] = $state([]);
    let init = $state(false);
    let collapsed = $state(true);

    const fetchStressCommands = async function () {
        try {
            const res = await fetch(`/api/v1/client/sct/${testRun.id}/stress_cmd/get`);
            const json = await res.json();
            if (json.status !== "ok") {
                throw new Error(json.response.arguments[0]);
            }

            stressCommands = json.response;
        } catch (e) {
            if (e instanceof Error) {
                sendMessage("error", e.message, "SctSetup::fetchStressCommands");
            } else {
                sendMessage("error", "Backend error during stress command fetch.", "SctSetup::fetchStressCommands");
                console.trace();
            }
        } finally {
            init = true;
        }
    };

    onMount(async () => {
        await fetchStressCommands();
    })
</script>

<div class="p-2">
    <div class="mb-2">
        <h4><button class="btn btn-sm btn-secondary d-inline-block me-2" onclick={() => (collapsed = !collapsed)}><Fa icon={collapsed ? faAngleUp : faAngleDown}/></button>Stress Commands
        </h4>
        <p class="text-muted" style="font-size: 0.8rem">
            Stress commands executed during the test run.
        </p>
        {#if stressCommands.length > 0 && init}
            <div class:d-none={collapsed} class="rounded bg-light-two p-1" style="max-height: 768px; overflow-y: scroll;">
                <table class="table table-striped table-responsive table-hover">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Command</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each stressCommands as cmd, idx}
                            <tr>
                                <td class="fw-bold">{idx+1}</td>
                                <td>
                                    <div class="input-group">
                                        <textarea class="form-control" style="resize: none" rows=4 disabled>{cmd.cmd}</textarea>
                                        <button class="d-none btn btn-success btn-sm" onclick={() => navigator.clipboard.writeText(cmd.cmd)}><Fa icon={faCopy}/></button>
                                    </div>
                                    <div class="d-flex">
                                        {#if cmd.log_name}
                                            <div>
                                                Log File: {cmd.log_name}
                                            </div>
                                        {/if}
                                        {#if cmd.loader_name}
                                            <div class="ms-auto">
                                                Node: {cmd.loader_name}
                                            </div>
                                        {/if}
                                    </div>
                                    {#if cmd.ts}
                                        <div class="text-muted" style="font-size: 0.75rem">
                                            Executed at {timestampToISODate(cmd.ts)}
                                        </div>
                                    {/if}
                                </td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        {:else if stressCommands.length == 0 && !init}
            <div class="text-center text-muted p-4">
                <span class="spinner-border spinner-border-sm"></span> Fetching stress commands...
            </div>
        {:else}
            <div class="text-center text-muted p-4">
                No Stress Commands were submitted to this run.
            </div>
        {/if}
    </div>
</div>

<style>
    .input-group:hover button{
        display: inline !important;
    }
</style>
