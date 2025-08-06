<script lang="ts">
    import { StatusBackgroundCSSClassMap } from "../../../Common/TestStatus";
    import type { TestRun } from "./Interfaces";

    interface Props {
        run: TestRun;
    }

    let { run }: Props = $props();

    const status = run.status?.toLowerCase();
    const badgeClass = getBadgeClass(status);
    const statusText = getStatusText(status);

    function getBadgeClass(status: string | undefined): string {
        const baseClass =
            StatusBackgroundCSSClassMap[status as keyof typeof StatusBackgroundCSSClassMap] || "bg-secondary";
        // Special case for running status to ensure text readability
        return status === "running" ? `${baseClass} text-dark` : baseClass;
    }

    function getStatusText(status: string | undefined): string {
        return status ? status.charAt(0).toUpperCase() + status.slice(1) : "Unknown";
    }
</script>

<span class="badge {badgeClass}">{statusText}</span>
