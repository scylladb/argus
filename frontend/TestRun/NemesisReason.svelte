<script lang="ts">
    import { NemesisStatuses } from "../Common/TestStatus";
    let { nemesis } = $props();
</script>

<li>
<span class="fw-bold">{nemesis.status != NemesisStatuses.SKIPPED ? "Failure" : "Skip"} reason</span>
<pre class="stacktrace overflow-scroll">
{nemesis.stack_trace}
</pre>
</li>

<style>
    .stacktrace {
        padding: 0.5rem;
        font-family: monospace;
        font-size: 12pt;
        background-color: #f0f0f0;
        border-radius: 0.25rem;
        width: 60em;
    }
</style>
