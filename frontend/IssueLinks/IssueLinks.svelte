<script lang="ts">
    import { onMount } from "svelte";
    import { fetchJson } from "../Common/ApiUtils";
    import IssueCard from "../Common/IssueCard.svelte";
    import LinkedRun from "./LinkedRun.svelte";
    import type { IssueLinks } from "../Common/IssueTypes";

    let { issueKey }: { issueKey: string } = $props();

    let result: IssueLinks | undefined = $state();
    let error = $state("");

    const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

    const summary = $derived.by(() => {
        const links = result?.links ?? [];
        const tests = new Set(links.map((link) => link.test_id)).size;
        const versions = new Set(links.map((link) => link.scylla_version || link.product_version).filter(Boolean)).size;
        const statuses = Object.entries(
            links.reduce((counts: Record<string, number>, link) => {
                counts[link.status] = (counts[link.status] ?? 0) + 1;
                return counts;
            }, {}),
        )
            .sort(([, lhs], [, rhs]) => rhs - lhs)
            .map(([status, count]) => `${count} ${status.replaceAll("_", " ")}`);
        return [plural(tests, "test"), plural(versions, "version"), ...statuses].join(" · ");
    });

    onMount(async () => {
        try {
            result = await fetchJson(`/api/v1/issues/${encodeURIComponent(issueKey)}/links`);
        } catch (e) {
            error = e instanceof Error ? e.message : String(e);
        }
    });
</script>

<div class="my-2">
    {#if error}
        <div class="alert alert-danger">{error}</div>
    {:else if !result}
        <div class="text-muted p-2">
            <span class="spinner-border spinner-border-sm"></span> Loading runs linked to {issueKey}…
        </div>
    {:else if !result.issue}
        <div class="alert alert-secondary">Argus holds no issue {issueKey.toUpperCase()}.</div>
    {:else}
        <IssueCard issue={result.issue} runId="" deleteEnabled={false} />
        {#if result.links.length > 0}
            <div class="mx-2 mt-3 mb-2">
                <h5 class="mb-0">{plural(result.links.length, "linked run")}</h5>
                <div class="small text-muted">{summary}</div>
            </div>
            <div class="run-list mx-2 p-2 d-flex flex-column gap-2 border rounded bg-light-three">
                <div class="row g-2 px-2 small text-muted text-uppercase d-none d-lg-flex">
                    <div class="col-lg-1">Status</div>
                    <div class="col-lg-5">Test</div>
                    <div class="col-lg-1">Build</div>
                    <div class="col-lg-2">Started</div>
                    <div class="col-lg-1">Version</div>
                </div>
                {#each result.links as link (link.run_id)}
                    <LinkedRun {link} />
                {/each}
            </div>
        {:else}
            <div class="alert alert-secondary m-2">No test runs are linked to {result.issue.key}.</div>
        {/if}
    {/if}
</div>

<style>
    .run-list {
        box-shadow: var(--bs-box-shadow-inset);
    }
</style>
