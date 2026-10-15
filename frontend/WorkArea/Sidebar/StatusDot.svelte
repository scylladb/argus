<script lang="ts">
    import { StatusBackgroundCSSClassMap } from "../../Common/TestStatus";

    interface Props {
        status?: string;
    }

    let { status }: Props = $props();

    const label = $derived(status ? status.replaceAll("_", " ") : "no runs yet");
    const colorClass = $derived(
        (StatusBackgroundCSSClassMap as Record<string, string>)[status ?? ""] ?? "bg-secondary-subtle"
    );
</script>

<span class="status-dot flex-shrink-0 {colorClass}" title={label}></span>
<span class="visually-hidden">Status: {label}.</span>

<style>
    .status-dot {
        display: inline-block;
        width: 0.75rem;
        height: 0.75rem;
        border-radius: 50%;
    }
</style>
