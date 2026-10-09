<script lang="ts">
    import { slide } from "svelte/transition";
    import { cubicInOut } from "svelte/easing";
    import Fa from "svelte-fa";
    import { faChevronDown, faChevronUp, faExternalLinkAlt } from "@fortawesome/free-solid-svg-icons";
    import TestRuns from "../WorkArea/TestRuns.svelte";
    import { StatusBadgeCSSClassMap } from "../Common/TestStatus";
    import { titleCase } from "../Common/TextUtils";
    import { timestampToISODate } from "../Common/DateUtils";
    import type { LinkedRun } from "../Common/IssueTypes";

    let { link }: { link: LinkedRun } = $props();

    let open = $state(false);
    const version = $derived(link.scylla_version || link.product_version);
    const location = $derived(link.build_id.split("/").slice(0, -1).join("/"));
    const linkedOn = $derived(link.linked_on ? `linked ${timestampToISODate(link.linked_on)}` : "");
</script>

<div class="linked-run bg-white rounded border px-2 py-1">
    <div class="row g-2 align-items-center">
        <div class="col-auto status-col">
            <span
                class="badge border text-uppercase {StatusBadgeCSSClassMap[link.status] ??
                    StatusBadgeCSSClassMap.unknown}">{titleCase(link.status.replaceAll("_", " "))}</span
            >
        </div>
        <div class="col min-w-0">
            <div class="fw-bold text-truncate" title={link.test_name}>{link.test_name}</div>
            <div class="small text-muted text-truncate">
                {[location, linkedOn].filter(Boolean).join(" · ")}
            </div>
        </div>
        <div class="w-100 d-lg-none"></div>
        <div class="col-auto col-lg-1">#{link.build_number}</div>
        <div class="col-auto col-lg-2 text-nowrap">{timestampToISODate(link.start_time)}</div>
        <div class="col-auto col-lg-1 text-truncate" title={version}>{version || "—"}</div>
        <div class="col-auto ms-auto actions-col d-flex justify-content-end">
            <div class="btn-group">
                <a class="btn btn-sm btn-primary text-nowrap" href={link.url}><Fa icon={faExternalLinkAlt} /> Open run</a>
                <button
                    class="btn btn-sm btn-outline-secondary text-nowrap"
                    aria-expanded={open}
                    onclick={() => (open = !open)}
                >
                    <Fa icon={open ? faChevronUp : faChevronDown} />
                    <span class="d-inline-grid text-start toggle-label">
                        <span class:invisible={open}>Show inline</span>
                        <span class:invisible={!open}>Hide</span>
                    </span>
                </button>
            </div>
        </div>
    </div>
    {#if open}
        <div class="mt-2" transition:slide={{ duration: 300, easing: cubicInOut }}>
            <TestRuns
                testId={link.test_id}
                additionalRuns={[link.run_id]}
                tab="details"
                showTitleBar={false}
                updateUrl={false}
                autoRefresh={false}
            />
        </div>
    {/if}
</div>

<style>
    .linked-run {
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }

    .min-w-0 {
        min-width: 0;
    }

    .toggle-label > span {
        grid-area: 1 / 1;
    }
</style>
