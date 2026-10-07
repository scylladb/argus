<script lang="ts">
    let { sourceRunId }: { sourceRunId: string } = $props();

    // The source of a local run often never reached Argus, so the line
    // links to it only when Argus has the run. Until the lookup answers, or
    // when it fails, the line shows the ID and claims nothing.
    let source: "unknown" | "found" | "missing" = $state("unknown");

    $effect(() => {
        const runId = sourceRunId;
        source = "unknown";
        fetch(`/api/v1/run/${runId}/type`)
            .then((res) => res.json())
            .then((body) => {
                if (runId !== sourceRunId || body.status !== "ok") {
                    return;
                }
                source = body.response.run_type === "unknown-does-not-exist" ? "missing" : "found";
            })
            .catch(() => {
                source = "unknown";
            });
    });
</script>

<li>
    <span class="fw-bold">Replayed from:</span>
    {#if source === "found"}
        <a href="/test_run/{sourceRunId}">{sourceRunId}</a>
    {:else if source === "missing"}
        {sourceRunId} <span class="text-muted">(not in Argus)</span>
    {:else}
        {sourceRunId}
    {/if}
</li>
