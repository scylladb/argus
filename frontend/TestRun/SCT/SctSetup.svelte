<script lang="ts">
    import Fa from "svelte-fa";
    import type { SCTTestRun } from "../TestRun.svelte";
    import { faCopy } from "@fortawesome/free-solid-svg-icons";
    import { timestampToISODate } from "../../Common/DateUtils";

    let {
        testRun
    }: { testRun: SCTTestRun} = $props();

</script>

<div class="p-2">
    <div class="mb-2">
        <h4>Stress Commands</h4>
        <p class="text-muted" style="font-size: 0.8rem">
            Stress commands executed during the test run.
        </p>
        <table class="table table-striped table-responsive table-hover">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Command</th>
                </tr>
            </thead>
            <tbody>
                {#each testRun.stress_commands as cmd, idx}
                    <tr>
                        <td class="fw-bold">{idx+1}</td>
                        <td>
                            <div class="input-group">
                                <input class="form-control" type="text" value="{cmd.cmd}" disabled>
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
</div>

<style>
    .input-group:hover button{
        display: inline !important;
    }
</style>
