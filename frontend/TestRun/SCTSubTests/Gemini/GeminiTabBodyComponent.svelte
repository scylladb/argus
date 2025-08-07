<script lang="ts">
    import { faCopy } from "@fortawesome/free-solid-svg-icons";
    import Fa from "svelte-fa";

    let { testRun } = $props();
</script>

<div
    class="tab-pane fade"
    id="nav-gemini-{testRun.id}"
    role="tabpanel"
>
    <div class="p-2">
        <div class="mb-1">
            <div class="input-group">
                <span class="input-group-text fw-bold">Gemini Command</span>
                <input
                    type="text"
                    class="form-control user-select-all"
                    disabled
                    value="{testRun.gemini_command}"
                />
                <button
                    class="btn btn-success"
                    type="button"
                    onclick={() => {
                        navigator.clipboard.writeText(
                            testRun.gemini_command
                        );
                    }}
                >
                    <Fa icon={faCopy} />
                </button>
            </div>
        </div>
        <div class="d-flex mb-2 p-2">
            <div class="w-50">
                <h5>Gemini Setup</h5>
                <ul class="border-start list-unstyled p-2">
                    <li><span class="fw-bold">Gemini Version: </span>{testRun.gemini_version}</li>
                    <li><span class="fw-bold">Gemini Seed: </span>{testRun.gemini_seed}</li>
                    <li><span class="fw-bold">Oracle Node: </span>{testRun.oracle_node_scylla_version} ({testRun.oracle_node_ami_id})</li>
                    <li><span class="fw-bold">Oracle Node Amount: </span>{testRun.oracle_nodes_count}</li>
                    <li><span class="fw-bold">Oracle Instance Type: </span>{testRun.oracle_node_instance_type}</li>
                </ul>
            </div>
            <div class="w-50">
                <h5>Gemini Results</h5>
                <ul class="border-start list-unstyled p-2">
                    <li><span class="fw-bold">Gemini Status: </span>{testRun.gemini_status}</li>
                    <li><span class="fw-bold">Write Ops: </span>{testRun.gemini_write_ops}</li>
                    <li><span class="fw-bold">Write Errors: </span>{testRun.gemini_write_errors}</li>
                    <li><span class="fw-bold">Read Ops: </span>{testRun.gemini_read_ops}</li>
                    <li><span class="fw-bold">Read Errors: </span>{testRun.gemini_read_errors}</li>
                </ul>
            </div>
        </div>
    </div>
</div>
