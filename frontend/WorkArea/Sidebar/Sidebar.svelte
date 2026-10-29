<script lang="ts">
    import { onMount } from "svelte";
    import Fa from "svelte-fa";
    import { faBars, faChartPie, faEyeSlash, faFolderOpen, faRotate } from "@fortawesome/free-solid-svg-icons";
    import { displayName, duplicateNames, pinnedFirst, sortTests } from "./sidebarSort";
    import { SidebarState, type Group, type Release, type SearchHit, type Test } from "./sidebarState.svelte";
    import { hideDrawer, isDrawer, offcanvas, showDrawer } from "./offcanvas";
    import SidebarRow from "./SidebarRow.svelte";
    import SidebarSearch from "./SidebarSearch.svelte";
    import ConfirmDeleteModal from "../../Common/ConfirmDeleteModal.svelte";
    import { fetchJson } from "../../Common/ApiUtils";
    import { sendMessage } from "../../Stores/AlertStore";

    interface Props {
        openTests?: string[];
        openRuns?: Record<string, string[]>;
        onToggleTest: (testId: string) => void;
        onOpenTest: (testId: string) => void;
        onOpenTests: (testIds: string[]) => void;
        onOpenRun: (testId: string, runId: string) => void;
        onCloseRun: (testId: string, runId: string) => void;
    }

    let { openTests = [], openRuns = {}, onToggleTest, onOpenTest, onOpenTests, onOpenRun, onCloseRun }: Props = $props();

    type Entry =
        | { kind: "release"; item: Release }
        | { kind: "group"; item: Group }
        | { kind: "test"; item: Test };

    const FIRST_ROW = Symbol("first row");

    const sidebar = new SidebarState();
    let drawer: HTMLElement | undefined = $state();
    let searchBox: HTMLElement | undefined = $state();
    let search: SidebarSearch | undefined = $state();
    let activeId: string | null = $state(null);
    let focusTarget: string | null = $state(null);
    let focusRequest = $state(0);
    let pending: { id: string | typeof FIRST_ROW; move: boolean } | null = $state(null);
    let deleteTarget: Entry | null = $state(null);
    let deleting = $state(false);

    const summary = $derived(sidebar.summary(sidebar.release));
    const releaseStats = $derived(sidebar.release ? sidebar.stats.get(sidebar.release.name) : undefined);
    const groupSummary = $derived(sidebar.group ? summary?.groups?.[sidebar.group.id] : undefined);

    const current = $derived.by(() => {
        if (sidebar.group) return sidebar.tests.get(sidebar.group.id);
        if (sidebar.release) return sidebar.groups.get(sidebar.release.id);
        return sidebar.releases;
    });

    const entries: Entry[] = $derived.by(() => {
        if (sidebar.group) {
            return sortTests(current?.data as Test[] ?? [], groupSummary?.tests).map((item) => ({ kind: "test", item }));
        }
        if (sidebar.release) return (current?.data as Group[] ?? []).map((item) => ({ kind: "group", item }));
        const releases = (current?.data as Release[] ?? []).filter(
            (release) => sidebar.showHidden || !sidebar.hidden.has(release.id)
        );
        return pinnedFirst(releases, sidebar.pinned).map((item) => ({ kind: "release", item }));
    });

    const hiddenCount = $derived((sidebar.releases.data ?? []).filter((release) => sidebar.hidden.has(release.id)).length);
    const canDelete = $derived(!!sidebar.release?.user_editable);

    const activeIndex = $derived(Math.max(0, entries.findIndex((entry) => entry.item.id === activeId)));
    const duplicates = $derived(duplicateNames(entries.map((entry) => entry.item)));
    const openSet = $derived(new Set(openTests));
    const openRunSet = $derived(
        new Set(Object.entries(openRuns).flatMap(([testId, runIds]) => (openSet.has(testId) ? runIds : [])))
    );
    const openIds = $derived([...openSet, ...openRunSet]);
    const emptyMessage = $derived(
        sidebar.group ? "No tests in this group." : sidebar.release ? "No groups in this release." : "No releases."
    );

    const focusRow = (index: number) => {
        const entry = entries[Math.min(Math.max(index, 0), entries.length - 1)];
        if (!entry) return;
        activeId = focusTarget = entry.item.id;
        focusRequest++;
    };

    $effect(() => {
        if (pending === null || entries.length === 0) return;
        const { id, move } = pending;
        pending = null;
        const index = Math.max(0, id === FIRST_ROW ? 0 : entries.findIndex((entry) => entry.item.id === id));
        const focused = document.activeElement;
        const focusIsFree = !focused || focused === document.body ||
            (!!drawer?.contains(focused) && !searchBox?.contains(focused));
        if (move && focusIsFree) {
            focusRow(index);
        } else {
            activeId = entries[index].item.id;
        }
    });

    const navigated = (id: string | typeof FIRST_ROW = FIRST_ROW, { move = true } = {}) => {
        activeId = focusTarget = null;
        pending = { id, move };
        search?.resetScope();
    };

    const activate = (entry: Entry | undefined) => {
        if (!entry) return;
        switch (entry.kind) {
        case "release":
            sidebar.enterRelease(entry.item);
            navigated();
            break;
        case "group":
            if (sidebar.release) sidebar.enterGroup(entry.item, sidebar.release);
            navigated();
            break;
        case "test": {
            const opening = !openSet.has(entry.item.id);
            onToggleTest(entry.item.id);
            if (opening) hideDrawer(drawer);
            break;
        }
        }
    };

    const goUp = () => {
        const from = sidebar.group ?? sidebar.release;
        if (!from) return;
        sidebar.up();
        navigated(from.id);
    };

    const showReleases = () => {
        const from = sidebar.release;
        sidebar.showReleases();
        navigated(from?.id);
    };

    const showGroups = () => {
        const from = sidebar.group;
        sidebar.group = null;
        navigated(from?.id);
    };

    const reload = () => {
        if (sidebar.group) {
            sidebar.loadTests(sidebar.group, { force: true });
        } else if (sidebar.release) {
            sidebar.loadGroups(sidebar.release, { force: true });
        } else {
            sidebar.loadReleases();
        }
    };

    const refresh = () => {
        if (sidebar.release) {
            sidebar.ensureStats(sidebar.release, { force: true });
        } else {
            for (const release of sidebar.releases.data ?? []) {
                if (sidebar.stats.get(release.name)?.error) sidebar.ensureStats(release);
            }
        }
        reload();
    };

    const togglePin = (release: Release) => {
        sidebar.togglePin(release);
        pending = { id: release.id, move: true };
    };

    const toggleHidden = (release: Release, index: number) => {
        const leaving = !sidebar.showHidden && !sidebar.hidden.has(release.id);
        const next = leaving ? (entries[index + 1] ?? entries[index - 1]) : entries[index];
        sidebar.toggleHidden(release);
        if (hiddenCount === 0) sidebar.showHidden = false;
        pending = { id: next?.item.id ?? FIRST_ROW, move: true };
    };

    const removedTests = (target: Entry): string[] => {
        if (target.kind === "test") return [target.item.id];
        if (target.kind === "group") return (sidebar.tests.get(target.item.id)?.data ?? []).map((test) => test.id);
        return [];
    };

    const confirmDelete = async () => {
        const target = deleteTarget;
        const release = sidebar.release;
        if (!target || !release || target.kind === "release") return;
        deleting = true;
        try {
            await fetchJson(`/api/v1/${target.kind}/${target.item.id}`, { method: "DELETE" });
            for (const testId of removedTests(target)) {
                if (openSet.has(testId)) onToggleTest(testId);
            }
            deleteTarget = null;
            sendMessage("success", `Deleted ${target.kind} ${displayName(target.item)}.`, "Sidebar::confirmDelete");
            if (target.kind === "test" && sidebar.group) {
                await sidebar.loadTests(sidebar.group, { force: true });
            } else {
                await sidebar.loadGroups(release, { force: true });
            }
            sidebar.ensureStats(release, { force: true });
        } catch (error) {
            sendMessage("error", error instanceof Error ? error.message : String(error), "Sidebar::confirmDelete");
        } finally {
            deleting = false;
        }
    };

    const hitStats = (hit: SearchHit) => {
        if (hit.type === "run") return hit.status ? { status: hit.status } : undefined;
        const data = sidebar.stats.get(hit.type === "release" ? hit.name : (hit.release?.name ?? ""))?.data;
        if (!data || "dormant" in data) return undefined;
        if (hit.type === "release") return { counts: data };
        if (hit.type === "group") return { counts: data.groups?.[hit.id] };
        return { status: data.groups?.[hit.group_id ?? ""]?.tests?.[hit.id]?.status };
    };

    const pick = (hit: SearchHit) => {
        if (hit.type === "test" && openSet.has(hit.id)) {
            onToggleTest(hit.id);
            return;
        }
        const runTestId = hit.test_id ?? hit.test?.id;
        if (hit.type === "run" && runTestId && openRunSet.has(hit.id)) {
            onCloseRun(runTestId, hit.id);
            return;
        }
        const testId = sidebar.locate(hit);
        if (testId && hit.type === "test") onOpenTest(testId);
        if (testId && hit.type === "run") onOpenRun(testId, hit.id);
        navigated(testId ?? FIRST_ROW, { move: false });
    };

    const handleListKey = (event: KeyboardEvent) => {
        if (event.altKey || event.ctrlKey || event.metaKey) return;
        switch (event.key) {
        case "ArrowDown":
            focusRow(activeIndex + 1);
            break;
        case "ArrowUp":
            focusRow(activeIndex - 1);
            break;
        case "Home":
            focusRow(0);
            break;
        case "End":
            focusRow(entries.length - 1);
            break;
        case "ArrowRight":
            if (entries[activeIndex]?.kind === "test") return;
            activate(entries[activeIndex]);
            break;
        case "ArrowLeft":
        case "Backspace":
            goUp();
            break;
        default:
            return;
        }
        event.preventDefault();
    };

    const isTyping = (target: EventTarget | null): boolean =>
        target instanceof HTMLElement &&
        (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

    const handleWindowKey = (event: KeyboardEvent) => {
        if (event.key !== "/" || event.altKey || event.ctrlKey || event.metaKey || isTyping(event.target)) return;
        event.preventDefault();
        if (isDrawer(drawer) && !drawer?.classList.contains("show")) {
            showDrawer(drawer);
        } else {
            search?.focus();
        }
    };

    const rowStats = (entry: Entry) => {
        if (entry.kind === "release") {
            const stats = sidebar.stats.get(entry.item.name);
            const data = stats?.data && !("dormant" in stats.data) ? stats.data : undefined;
            return { stats: data, loading: !!stats?.promise && !data, error: stats?.error };
        }
        if (entry.kind === "group") {
            return {
                stats: summary?.groups?.[entry.item.id],
                loading: !!releaseStats?.promise && !summary,
                error: summary ? undefined : releaseStats?.error,
            };
        }
        return { stats: undefined, loading: false, error: undefined };
    };

    const assigneesFor = (entry: Entry): string[] => {
        if (entry.kind === "group" && sidebar.release) {
            return sidebar.groupAssignees.get(sidebar.release.id)?.[entry.item.id] ?? [];
        }
        if (entry.kind === "test" && sidebar.group) {
            return sidebar.testAssignees.get(sidebar.group.id)?.[entry.item.id] ?? [];
        }
        return [];
    };

    onMount(() => {
        sidebar.loadReleases();
    });
</script>

<svelte:window onkeydown={handleWindowKey} />

<aside
    class="offcanvas-md offcanvas-start col-md-4 col-xl-3"
    id="workspace-sidebar"
    tabindex="-1"
    aria-labelledby="workspace-sidebar-title"
    bind:this={drawer}
    use:offcanvas={{ onShown: () => search?.focus() }}
>
    <div class="offcanvas-header border-bottom">
        <h2 class="offcanvas-title h5" id="workspace-sidebar-title">Workspace</h2>
        <button type="button" class="btn-close" data-bs-dismiss="offcanvas" data-bs-target="#workspace-sidebar" aria-label="Close"></button>
    </div>
    <div class="sidebar-panel d-flex flex-column flex-grow-1 bg-body border rounded shadow-sm">
        <div class="p-2 border-bottom" bind:this={searchBox}>
            <SidebarSearch bind:this={search} scope={sidebar.release} {openIds} statsFor={hitStats} onPick={pick} />
        </div>
        <div class="d-flex align-items-center gap-2 px-3 py-2 border-bottom">
            <nav aria-label="breadcrumb" class="flex-grow-1 min-w-0">
                <ol class="breadcrumb small mb-0">
                    {#if sidebar.release}
                        <li class="breadcrumb-item">
                            <button type="button" class="btn btn-link btn-sm p-0 align-baseline" onclick={showReleases}>Releases</button>
                        </li>
                        {#if sidebar.group}
                            <li class="breadcrumb-item">
                                <button type="button" class="btn btn-link btn-sm p-0 align-baseline" onclick={showGroups}>
                                    {displayName(sidebar.release)}
                                </button>
                            </li>
                            <li class="breadcrumb-item active text-break" aria-current="page">{displayName(sidebar.group)}</li>
                        {:else}
                            <li class="breadcrumb-item active text-break" aria-current="page">{displayName(sidebar.release)}</li>
                        {/if}
                    {:else}
                        <li class="breadcrumb-item active" aria-current="page">Releases</li>
                    {/if}
                </ol>
            </nav>
            {#if sidebar.release && !sidebar.group}
                <a class="btn btn-sm btn-outline-secondary" href="/dashboard/{sidebar.release.name}" title="Release dashboard">
                    <Fa icon={faChartPie} /><span class="visually-hidden">Release dashboard</span>
                </a>
            {/if}
            {#if sidebar.group}
                <button
                    type="button"
                    class="btn btn-sm btn-outline-secondary"
                    title="Open all tests"
                    disabled={entries.length === 0}
                    onclick={() => {
                        onOpenTests(entries.map((entry) => entry.item.id));
                        hideDrawer(drawer);
                    }}
                >
                    <Fa icon={faFolderOpen} /><span class="visually-hidden">Open all tests</span>
                </button>
            {/if}
            {#if !sidebar.release && hiddenCount > 0}
                <button
                    type="button"
                    class="btn btn-sm btn-outline-secondary text-nowrap"
                    class:active={sidebar.showHidden}
                    title={sidebar.showHidden ? "Hide the hidden releases" : "Show the hidden releases"}
                    aria-label={`Show hidden releases (${hiddenCount})`}
                    aria-pressed={sidebar.showHidden}
                    onclick={() => (sidebar.showHidden = !sidebar.showHidden)}
                >
                    <Fa icon={faEyeSlash} /> {hiddenCount}
                </button>
            {/if}
            <button type="button" class="btn btn-sm btn-outline-secondary" title="Refresh" onclick={refresh}>
                <Fa icon={faRotate} /><span class="visually-hidden">Refresh</span>
            </button>
        </div>
        <div class="sidebar-list flex-grow-1">
            {#if current?.error && !current?.data}
                <div class="p-3 text-center small">
                    <div class="text-danger-emphasis mb-2">Couldn't load this list: {current.error}</div>
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick={reload}>Retry</button>
                </div>
            {:else if (current?.loading || !current) && entries.length === 0}
                <div class="p-3 text-center small text-body-secondary">
                    <span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Loading…
                </div>
            {:else if entries.length === 0}
                <div class="p-3 text-center small text-body-secondary">{emptyMessage}</div>
            {:else}
                <ul class="list-unstyled m-0">
                    {#each entries as entry, index (entry.item.id)}
                        {@const name = displayName(entry.item)}
                        {@const stats = rowStats(entry)}
                        {@const testStatus = entry.kind === "test" ? groupSummary?.tests?.[entry.item.id] : undefined}
                        <li>
                            <SidebarRow
                                kind={entry.kind}
                                {name}
                                subtitle={duplicates.has(name) && name !== entry.item.name ? entry.item.name : null}
                                active={index === activeIndex}
                                pressed={entry.kind === "test" && openSet.has(entry.item.id)}
                                stats={stats.stats}
                                statsLoading={stats.loading}
                                statsError={stats.error}
                                status={testStatus?.status}
                                startTime={testStatus?.start_time}
                                pinned={entry.kind === "release" ? sidebar.pinned.has(entry.item.id) : undefined}
                                onTogglePin={entry.kind === "release" ? () => togglePin(entry.item) : undefined}
                                hidden={entry.kind === "release" ? sidebar.hidden.has(entry.item.id) : undefined}
                                onToggleHidden={entry.kind === "release" ? () => toggleHidden(entry.item, index) : undefined}
                                onDelete={canDelete && entry.kind !== "release" ? () => (deleteTarget = entry) : undefined}
                                dormant={entry.kind === "release" && entry.item.dormant}
                                assignees={assigneesFor(entry)}
                                focusRequest={focusTarget === entry.item.id ? focusRequest : 0}
                                onKeydown={handleListKey}
                                onActivate={() => {
                                    activeId = entry.item.id;
                                    activate(entry);
                                }}
                                onFocus={() => (activeId = entry.item.id)}
                            />
                        </li>
                    {/each}
                </ul>
            {/if}
        </div>
    </div>
</aside>

{#if deleteTarget && deleteTarget.kind !== "release"}
    {@const target = deleteTarget}
    <ConfirmDeleteModal
        heading={`Delete ${target.kind} ${displayName(target.item)}`}
        confirmName={target.item.name}
        working={deleting}
        onConfirm={confirmDelete}
        onCancel={() => (deleteTarget = null)}
    >
        <p>
            This removes the {target.kind} <span class="fw-bold">{displayName(target.item)}</span>{target.kind === "group"
                ? ", all its tests and their runs"
                : " and all its runs"}. This cannot be undone.
        </p>
    </ConfirmDeleteModal>
{/if}

<button
    type="button"
    class="drawer-toggle btn btn-primary rounded-circle shadow d-md-none position-fixed bottom-0 start-0 m-3"
    data-bs-toggle="offcanvas"
    data-bs-target="#workspace-sidebar"
    aria-controls="workspace-sidebar"
    aria-label="Open the workspace sidebar"
>
    <Fa icon={faBars} />
</button>

<style>
    .sidebar-list {
        overflow-y: auto;
        min-height: 0;
    }

    .min-w-0 {
        min-width: 0;
    }

    .drawer-toggle {
        width: 3.5rem;
        height: 3.5rem;
        z-index: 1040;
    }

    @media (max-width: 767.98px) {
        .sidebar-panel {
            border: 0 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            min-height: 0;
        }
    }

    @media (min-width: 768px) {
        .sidebar-panel {
            position: sticky;
            top: 1rem;
            height: calc(100vh - 2rem);
        }
    }
</style>
