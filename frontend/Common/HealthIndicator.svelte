<script lang="ts">
    import { onDestroy, onMount } from "svelte";

    interface FailingCheck {
        name: string;
        severity: string;
        status: string;
    }

    interface HealthSummary {
        enabled: boolean;
        status: "healthy" | "degraded" | "unhealthy" | "unknown";
        failing: FailingCheck[];
    }

    const POLL_INTERVAL_MS = 5 * 60 * 1000;
    const STATUS_COLOR: Record<string, string> = {
        unhealthy: "text-danger",
        degraded: "text-warning",
        unknown: "text-secondary",
    };

    let summary: HealthSummary | null = $state(null);
    let pollTimer: ReturnType<typeof setInterval> | undefined;

    const visible = $derived(summary !== null && summary.enabled && summary.status !== "healthy");
    const label = $derived.by(() => {
        if (!summary || summary.status === "unknown") {
            return "Argus health status unknown";
        }
        return `Argus dependencies ${summary.status}: ${summary.failing.map((check) => check.name).join(", ")}`;
    });
    const details = $derived.by(() => {
        if (!summary || summary.status === "unknown") {
            return "The Argus health process does not answer";
        }
        return summary.failing.map((check) => `${check.name}: ${check.status}`).join("\n");
    });

    const refresh = async function () {
        try {
            const response = await fetch("/api/v1/health/summary");
            const body = await response.json();
            if (body.status === "ok") {
                summary = body.response;
            }
        } catch (error) {
            console.warn("The health summary is not available", error);
        }
    };

    onMount(() => {
        refresh();
        pollTimer = setInterval(refresh, POLL_INTERVAL_MS);
    });

    onDestroy(() => {
        clearInterval(pollTimer);
    });
</script>

{#if visible && summary}
    <span class="nav-link" role="img" data-health-indicator aria-label={label} title={details}>
        <i class="fas fa-heartbeat {STATUS_COLOR[summary.status]}" aria-hidden="true"></i>
    </span>
{/if}
