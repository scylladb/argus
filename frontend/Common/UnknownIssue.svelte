<script lang="ts">
    import type { Issue } from "./IssueTypes";

    interface Props {
        issue: Issue;
    }

    let { issue }: Props = $props();
</script>

<div class="bg-white rounded p-2">
    <pre class="p-1 code monospace" style="white-space: pre-wrap">{JSON.stringify(issue, null, 2)}</pre>
</div>
