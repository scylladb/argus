<!-- New StackTracePreview Component -->
<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import { TestRun } from "./Interfaces";
    interface Props {
        run: TestRun;
    }

    let { run }: Props = $props();
    const dispatch = createEventDispatcher();
    let showFull = $state(false);

    function getStackTracePreview(stackTrace: string): string {
        return stackTrace ? stackTrace.split("\n").slice(0, 3).join("\n") : "";
    }

    function hasMoreLines(stackTrace: string): boolean {
        return stackTrace ? stackTrace.split("\n").length > 3 : false;
    }
</script>

<div class="stack-trace-container">
    <pre class="stack-trace-preview" class:hidden={showFull}>{getStackTracePreview(run.stack_trace || "")}</pre>
    <pre class="stack-trace-full" class:hidden={!showFull}>{run.stack_trace}</pre>
    {#if hasMoreLines(run.stack_trace || "")}
        <button class="btn btn-sm btn-outline-secondary mt-1" onclick={() => (showFull = !showFull)}>
            {showFull ? "Show Less" : "Show More"}
        </button>
    {/if}
</div>

<style>
    .stack-trace-preview,
    .stack-trace-full {
        font-size: 0.8rem;
        margin-bottom: 0;
        background-color: #f8f9fa;
        padding: 0.25rem;
        border-radius: 0.25rem;
        white-space: pre-wrap;
        word-break: break-word;
    }
    .stack-trace-preview {
        max-height: 4.5em;
        overflow: hidden;
    }
    .stack-trace-full {
        max-height: 200px;
        overflow-y: auto;
    }
    .hidden {
        display: none;
    }
    .stack-trace-container {
        position: relative;
    }
</style>
