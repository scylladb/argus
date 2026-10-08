<script lang="ts">
    import Fa from "svelte-fa";
    import { faChevronRight, faThumbtack, faTriangleExclamation } from "@fortawesome/free-solid-svg-icons";
    import { timestampToISODate } from "../../Common/DateUtils";
    import AssigneeList from "../AssigneeList.svelte";
    import StatusDot from "./StatusDot.svelte";
    import StatusSummary from "./StatusSummary.svelte";
    import type { StatusCounts } from "./sidebarSort";

    interface Props {
        kind: "release" | "group" | "test";
        name: string;
        subtitle?: string | null;
        active?: boolean;
        pressed?: boolean;
        stats?: StatusCounts;
        statsLoading?: boolean;
        statsError?: string;
        status?: string;
        startTime?: string | null;
        pinned?: boolean;
        onTogglePin?: () => void;
        dormant?: boolean;
        assignees?: string[];
        focusRequest?: number;
        onActivate: () => void;
        onKeydown?: (event: KeyboardEvent) => void;
        onFocus?: () => void;
        onHover?: () => void;
    }

    let {
        kind,
        name,
        subtitle = null,
        active = false,
        pressed = false,
        stats,
        statsLoading = false,
        statsError,
        status,
        startTime = null,
        pinned,
        onTogglePin,
        dormant = false,
        assignees = [],
        focusRequest = 0,
        onActivate,
        onKeydown,
        onFocus,
        onHover,
    }: Props = $props();

    let button: HTMLButtonElement | undefined = $state();

    $effect(() => {
        if (focusRequest > 0) button?.focus();
    });
</script>

<div class="d-flex border-bottom">
    <button
        bind:this={button}
        type="button"
        class="sidebar-row btn flex-grow-1 min-w-0 text-start rounded-0 border-0 px-3 py-2"
        class:open-test={pressed}
        tabindex={active ? 0 : -1}
        aria-pressed={kind === "test" ? pressed : undefined}
        onclick={() => onActivate()}
        onkeydown={(event) => onKeydown?.(event)}
        onfocus={() => {
            onFocus?.();
            onHover?.();
        }}
        onpointerenter={() => onHover?.()}
    >
        <span class="d-flex align-items-center gap-2">
            {#if kind === "test"}
                <StatusDot {status} />
            {/if}
            <span class="d-flex flex-column flex-grow-1 min-w-0">
                <span class="d-flex align-items-center gap-2">
                    <span class="row-name text-break">{name}</span>
                    {#if dormant}
                        <span class="badge text-bg-secondary">dormant</span>
                    {/if}
                </span>
                {#if subtitle}
                    <span class="small text-body-secondary text-break">{subtitle}</span>
                {/if}
                {#if startTime}
                    <span class="small text-body-secondary">{timestampToISODate(startTime)}</span>
                {/if}
                {#if stats}
                    <span class="d-flex mt-1"><StatusSummary {stats} /></span>
                {:else if statsLoading}
                    <span class="mt-1">
                        <span class="spinner-border spinner-border-sm text-secondary" role="status">
                            <span class="visually-hidden">Loading stats</span>
                        </span>
                    </span>
                {:else if statsError}
                    <span class="mt-1 small text-danger-emphasis" title={statsError}>
                        <Fa icon={faTriangleExclamation} /> Stats unavailable
                    </span>
                {/if}
            </span>
            {#if assignees.length > 0}
                <span class="flex-shrink-0"><AssigneeList {assignees} /></span>
            {/if}
            {#if kind !== "test"}
                <span class="text-body-tertiary flex-shrink-0"><Fa icon={faChevronRight} /></span>
            {/if}
        </span>
    </button>
    {#if pinned !== undefined}
        <button
            type="button"
            class="pin-toggle btn rounded-0 border-0 px-2"
            class:is-pinned={pinned}
            tabindex={active ? 0 : -1}
            aria-pressed={pinned}
            aria-label={`Pin ${name} to the top`}
            title={pinned ? "Unpin" : "Pin to the top"}
            onclick={() => onTogglePin?.()}
            onkeydown={(event) => onKeydown?.(event)}
        >
            <Fa icon={faThumbtack} />
        </button>
    {/if}
</div>

<style>
    .sidebar-row {
        --bs-btn-hover-bg: var(--bs-tertiary-bg);
        --bs-btn-active-bg: var(--bs-secondary-bg);
        color: var(--bs-body-color);
    }

    .sidebar-row:focus-visible {
        outline: 2px solid var(--bs-primary);
        outline-offset: -2px;
    }

    .pin-toggle {
        --bs-btn-hover-bg: var(--bs-tertiary-bg);
        color: var(--bs-tertiary-color);
    }

    .pin-toggle.is-pinned {
        color: var(--bs-primary);
    }

    .pin-toggle:focus-visible {
        outline: 2px solid var(--bs-primary);
        outline-offset: -2px;
    }

    .open-test {
        background-color: var(--bs-primary-bg-subtle);
        color: var(--bs-primary-text-emphasis);
        box-shadow: inset 3px 0 0 var(--bs-primary);
    }

    .min-w-0 {
        min-width: 0;
    }
</style>
