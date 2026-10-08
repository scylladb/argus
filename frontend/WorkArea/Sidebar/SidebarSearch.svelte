<script lang="ts">
    import { tick } from "svelte";
    import MultiSelect from "svelte-multiselect";
    import Fa from "svelte-fa";
    import { faCheck, faMagnifyingGlass, faXmark } from "@fortawesome/free-solid-svg-icons";
    import { displayName, type StatusCounts } from "./sidebarSort";
    import { searchPage, type Release, type SearchHit, type SearchOption } from "./sidebarState.svelte";
    import StatusDot from "./StatusDot.svelte";
    import StatusSummary from "./StatusSummary.svelte";

    interface HitStats {
        status?: string;
        counts?: StatusCounts;
    }

    interface Props {
        scope: Release | null;
        openTests?: string[];
        statsFor?: (hit: SearchHit) => HitStats | undefined;
        onPick: (hit: SearchHit) => void;
    }

    let { scope, openTests = [], statsFor, onPick }: Props = $props();

    const TYPE_LABELS: Record<SearchHit["type"], string> = {
        release: "Release",
        group: "Group",
        test: "Test",
        run: "Run",
    };

    let query = $state("");
    let open = $state(false);
    let selected: SearchOption[] = $state([]);
    let input: HTMLInputElement | null = $state(null);
    let widenedFrom: string | null = $state(null);
    let held = $state<{ scope: Release | null } | null>(null);

    const liveScope = $derived(scope && scope.id !== widenedFrom ? scope : null);
    const activeScope = $derived(open && held ? held.scope : liveScope);
    const scopeId = $derived(activeScope?.id ?? null);
    const openSet = $derived(new Set(openTests));
    const emptyMessage = $derived(
        !scopeId && /(^|\s)-?(status|istatus|assignee):/i.test(query)
            ? "status:, istatus: and assignee: work inside one release. Open a release or add release:<name>."
            : "Nothing matches"
    );

    export const focus = () => input?.focus();

    const hitPath = (hit: SearchHit): string =>
        [hit.release, hit.group]
            .filter((ref) => ref && ref.id !== hit.id)
            .map((ref) => displayName(ref!))
            .join(" / ");

    const pick = (option: SearchOption) => {
        selected = [];
        onPick(option.hit);
    };

    // Both buttons leave the DOM before the click reaches the dropdown's
    // outside-click listener on window, which would then close it.
    const clear = (event: MouseEvent) => {
        event.stopPropagation();
        query = "";
        input?.focus();
    };

    const widen = async (event: MouseEvent) => {
        event.stopPropagation();
        widenedFrom = scope?.id ?? null;
        held = { scope: null };
        open = true;
        await tick();
        input?.focus();
    };
</script>

<div class="workspace-search">
    <label class="visually-hidden" for="workspace-search">Search the workspace</label>
    {#key scopeId}
        <MultiSelect
            id="workspace-search"
            bind:selected
            bind:searchText={query}
            bind:open
            bind:input
            loadOptions={{
                fetch: (params) => searchPage(params, scopeId),
                debounceMs: 200,
                batchSize: 30,
                onOpen: false,
            }}
            placeholder={scopeId ? "Search this release ( / )" : "Search releases, groups, tests ( / )"}
            noMatchingOptionsMsg={emptyMessage}
            expandIconPosition="none"
            resetFilterOnAdd={false}
            onopen={() => (held = { scope: liveScope })}
            onclose={() => (held = null)}
            onadd={({ option }) => pick(option)}
        >
            {#snippet beforeInput()}
                <span class="text-body-tertiary ps-1 pe-2" aria-hidden="true"><Fa icon={faMagnifyingGlass} /></span>
                {#if activeScope}
                    <span class="badge text-bg-primary d-inline-flex align-items-center gap-1 me-1 text-nowrap">
                        in {displayName(activeScope)}
                        <button
                            type="button"
                            class="btn btn-sm p-0 border-0 lh-1 text-reset"
                            aria-label="Search all releases"
                            title="Search all releases"
                            onclick={widen}
                        >
                            <Fa icon={faXmark} />
                        </button>
                    </span>
                {/if}
            {/snippet}
            {#snippet afterInput()}
                {#if query}
                    <button
                        type="button"
                        class="btn btn-sm p-0 px-1 border-0 lh-1 text-body-tertiary"
                        aria-label="Clear the search"
                        title="Clear the search"
                        onclick={clear}
                    >
                        <Fa icon={faXmark} />
                    </button>
                {/if}
            {/snippet}
            {#snippet option({ option })}
                {@const stats = statsFor?.(option.hit)}
                <span class="d-flex align-items-start gap-2 w-100 min-w-0 py-1">
                    <span class="badge text-bg-secondary flex-shrink-0 mt-1">{TYPE_LABELS[option.hit.type]}</span>
                    {#if stats?.status}
                        <span class="d-inline-flex flex-shrink-0 mt-1"><StatusDot status={stats.status} /></span>
                    {/if}
                    <span class="d-flex flex-column flex-grow-1 min-w-0">
                        <span class="text-break">{option.label}</span>
                        {#if hitPath(option.hit)}
                            <span class="small text-body-secondary text-break">{hitPath(option.hit)}</span>
                        {/if}
                        {#if stats?.counts}
                            <span class="d-flex mt-1"><StatusSummary stats={stats.counts} /></span>
                        {/if}
                    </span>
                    {#if option.hit.type === "test" && openSet.has(option.hit.id)}
                        <span class="text-success-emphasis flex-shrink-0 mt-1" title="Open in the panel">
                            <Fa icon={faCheck} /><span class="visually-hidden">Open in the panel</span>
                        </span>
                    {/if}
                </span>
            {/snippet}
        </MultiSelect>
    {/key}
</div>

<style>
    .workspace-search {
        --sms-bg: var(--bs-body-bg);
        --sms-options-bg: var(--bs-body-bg);
        --sms-text-color: var(--bs-body-color);
        --sms-placeholder-color: var(--bs-secondary-color);
        --sms-placeholder-opacity: 1;
        --sms-border: var(--bs-border-width) solid var(--bs-border-color);
        --sms-focus-border: var(--bs-border-width) solid var(--bs-primary);
        --sms-border-radius: var(--bs-border-radius);
        --sms-active-color: var(--bs-primary-bg-subtle);
        --sms-min-height: calc(1.5em + 0.75rem + 2px);
        --sms-padding: 0.375rem 0.5rem;
        --sms-options-z-index: 1060;
        --sms-options-max-height: 60vh;
    }

    .workspace-search :global(ul.selected),
    .workspace-search :global(ul.options) {
        padding-left: 0;
        margin-bottom: 0;
    }

    .min-w-0 {
        min-width: 0;
    }
</style>
