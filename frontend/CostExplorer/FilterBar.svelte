<script lang="ts">
    import { onMount, untrack } from "svelte";
    import MultiSelect, { type ObjectOption } from "svelte-multiselect";
    import Fa from "svelte-fa";
    import { faBusinessTime, faFolder, faVial } from "@fortawesome/free-solid-svg-icons";
    import { StatusBadgeCSSClassMap, TestStatus } from "../Common/TestStatus";
    import { displayName, loadGroups, loadReleases, loadTests } from "./api";
    import { BREAKDOWNS, GRANULARITIES, RANGE_PRESETS, TIERS, fitRange, presetRange, type ListKey, type Span } from "./filters";
    import type { ExplorerFilters, NamedEntity } from "./types";

    interface Props {
        filters: ExplorerFilters;
        backends?: string[];
        span?: Span | null;
    }

    let { filters = $bindable(), backends = [], span = null }: Props = $props();

    type Choice = ObjectOption & { value: string };
    const PLUGINS = ["scylla-cluster-tests", "driver-matrix-tests", "sirenada", "generic"];
    const TIER_LABELS: Record<string, string> = { spot: "Spot", "on-demand": "On-demand" };

    let releases: NamedEntity[] = $state([]);
    let groups: NamedEntity[] = $state([]);
    let tests: NamedEntity[] = $state([]);

    const choice = (value: string, label: string = value): Choice => ({ label, value });
    const entityChoices = (entities: NamedEntity[], value: (entity: NamedEntity) => string): Choice[] =>
        entities.map((entity) => choice(value(entity), displayName(entity)));
    const chosen = (options: Choice[], values: string[]): Choice[] =>
        values.map((value) => options.find((option) => option.value === value) ?? choice(value));

    const releaseOptions = $derived(entityChoices(releases, (release) => release.name));
    const groupOptions = $derived(entityChoices(groups, (group) => group.id));
    const testOptions = $derived(entityChoices(tests, (test) => test.id));
    const backendOptions = $derived([...new Set([...backends, ...filters.backends])].sort().map((backend) => choice(backend)));
    const pluginOptions = PLUGINS.map((plugin) => choice(plugin));
    const tierOptions = TIERS.map((tier) => choice(tier, TIER_LABELS[tier]));
    const statusOptions = Object.values(TestStatus).map((status: string) => choice(status, status.replaceAll("_", " ")));
    const statusClass = (status: string): string =>
        (StatusBadgeCSSClassMap as Record<string, string>)[status] ?? "text-bg-secondary";

    const add = (key: ListKey, value: string) => {
        if (!filters[key].includes(value)) filters[key] = [...filters[key], value];
    };
    const remove = (key: ListKey, value: string) => {
        filters[key] = filters[key].filter((item) => item !== value);
    };
    const clear = (key: ListKey) => {
        filters[key] = [];
    };
    const keep = (key: ListKey, available: NamedEntity[]) => {
        const ids = new Set(available.map((entity) => entity.id));
        const kept = filters[key].filter((id) => ids.has(id));
        if (kept.length !== filters[key].length) filters[key] = kept;
    };
    const prune = (key: ListKey) => untrack(() => { if (filters[key].length > 0) clear(key); });
    let groupLoad = 0;
    let testLoad = 0;

    const presetActive = (days: number): boolean => {
        const range = presetRange(days);
        return filters.from === range.from && filters.to === range.to;
    };

    const applyPreset = (days: number) => {
        const range = presetRange(days);
        filters.from = range.from;
        filters.to = range.to;
    };

    const fitToReleases = () => {
        if (!span) return;
        const range = fitRange(span);
        filters.from = range.from;
        filters.to = range.to;
    };

    onMount(async () => {
        releases = await loadReleases();
    });

    $effect(() => {
        const load = ++groupLoad;
        if (filters.releaseNames.length === 0) {
            groups = [];
            prune("groupIds");
            return;
        }
        const selected = releases.filter((release) => filters.releaseNames.includes(release.name));
        if (selected.length === 0) {
            groups = [];
            return;
        }
        Promise.all(selected.map((release) => loadGroups(release.id))).then((loaded) => {
            if (load !== groupLoad) return;
            groups = loaded.flat();
            keep("groupIds", groups);
        });
    });

    $effect(() => {
        const load = ++testLoad;
        const ids = filters.groupIds;
        if (ids.length === 0) {
            tests = [];
            prune("testIds");
            return;
        }
        Promise.all(ids.map((id) => loadTests(id))).then((loaded) => {
            if (load !== testLoad) return;
            tests = loaded.flat();
            keep("testIds", tests);
        });
    });
</script>

{#snippet releaseItem({ option }: { option: Choice })}
    <span class="item" title={option.label}><Fa icon={faBusinessTime} class="text-body-tertiary" /><span class="text-truncate">{option.label}</span></span>
{/snippet}
{#snippet groupItem({ option }: { option: Choice })}
    <span class="item" title={option.label}><Fa icon={faFolder} class="text-body-tertiary" /><span class="text-truncate">{option.label}</span></span>
{/snippet}
{#snippet testItem({ option }: { option: Choice })}
    <span class="item" title={option.label}><Fa icon={faVial} class="text-body-tertiary" /><span class="text-truncate">{option.label}</span></span>
{/snippet}
{#snippet statusItem({ option }: { option: Choice })}
    <span class="badge rounded-pill {statusClass(option.value)}">{option.label}</span>
{/snippet}

<div class="d-flex flex-wrap align-items-end gap-2">
    <div class="d-flex flex-column">
        <label class="form-label small text-body-secondary mb-1" for="costFrom">Range</label>
        <div class="d-flex flex-wrap align-items-center gap-2">
            <div class="btn-group btn-group-sm" role="group" aria-label="Range presets">
                {#each RANGE_PRESETS as days (days)}
                    <button
                        type="button"
                        class="btn btn-outline-primary"
                        class:active={presetActive(days)}
                        onclick={() => applyPreset(days)}
                    >
                        {days}d
                    </button>
                {/each}
            </div>
            <input id="costFrom" type="date" class="form-control form-control-sm w-auto" max={filters.to}
                bind:value={filters.from} aria-label="From" />
            <span class="text-body-secondary small">to</span>
            <input type="date" class="form-control form-control-sm w-auto" min={filters.from}
                bind:value={filters.to} aria-label="To" />
            {#if span}
                <button type="button" class="btn btn-link btn-sm p-0" onclick={fitToReleases}>Fit to releases</button>
            {/if}
        </div>
    </div>
    <div class="d-flex flex-column picker grow">
        <label class="form-label small text-body-secondary mb-1" for="costRelease">Release</label>
        <MultiSelect id="costRelease" options={releaseOptions} selected={chosen(releaseOptions, filters.releaseNames)} key={(option) => option.value} allowEmpty
            placeholder="All releases" children={releaseItem} onadd={({ option }) => add("releaseNames", option.value)}
            onremove={({ option }) => remove("releaseNames", option.value)} onremoveAll={() => clear("releaseNames")} />
    </div>
    <div class="d-flex flex-column picker grow">
        <label class="form-label small text-body-secondary mb-1" for="costGroup">Group</label>
        <MultiSelect id="costGroup" options={groupOptions} selected={chosen(groupOptions, filters.groupIds)} key={(option) => option.value} allowEmpty
            placeholder="All groups" children={groupItem} disabled={filters.releaseNames.length === 0} onadd={({ option }) => add("groupIds", option.value)}
            onremove={({ option }) => remove("groupIds", option.value)} onremoveAll={() => clear("groupIds")} />
    </div>
    <div class="d-flex flex-column picker grow">
        <label class="form-label small text-body-secondary mb-1" for="costTest">Test</label>
        <MultiSelect id="costTest" options={testOptions} selected={chosen(testOptions, filters.testIds)} key={(option) => option.value} allowEmpty
            placeholder="All tests" children={testItem} disabled={filters.groupIds.length === 0} onadd={({ option }) => add("testIds", option.value)}
            onremove={({ option }) => remove("testIds", option.value)} onremoveAll={() => clear("testIds")} />
    </div>
    <div class="d-flex flex-column picker">
        <label class="form-label small text-body-secondary mb-1" for="costBackend">Backend</label>
        <MultiSelect id="costBackend" options={backendOptions} selected={chosen(backendOptions, filters.backends)} key={(option) => option.value} allowEmpty
            placeholder="All" onadd={({ option }) => add("backends", option.value)}
            onremove={({ option }) => remove("backends", option.value)} onremoveAll={() => clear("backends")} />
    </div>
    <div class="d-flex flex-column picker">
        <label class="form-label small text-body-secondary mb-1" for="costPlugin">Source</label>
        <MultiSelect id="costPlugin" options={pluginOptions} selected={chosen(pluginOptions, filters.plugins)} key={(option) => option.value} allowEmpty
            placeholder="All" onadd={({ option }) => add("plugins", option.value)}
            onremove={({ option }) => remove("plugins", option.value)} onremoveAll={() => clear("plugins")} />
    </div>
    <div class="d-flex flex-column picker">
        <label class="form-label small text-body-secondary mb-1" for="costStatus">Status</label>
        <MultiSelect id="costStatus" options={statusOptions} selected={chosen(statusOptions, filters.statuses)} key={(option) => option.value} allowEmpty
            placeholder="All" children={statusItem} onadd={({ option }) => add("statuses", option.value)}
            onremove={({ option }) => remove("statuses", option.value)} onremoveAll={() => clear("statuses")} />
    </div>
    <div class="d-flex flex-column picker">
        <label class="form-label small text-body-secondary mb-1" for="costTier">Lifecycle</label>
        <MultiSelect id="costTier" options={tierOptions} selected={chosen(tierOptions, filters.tiers)} key={(option) => option.value} allowEmpty
            placeholder="All" onadd={({ option }) => add("tiers", option.value)}
            onremove={({ option }) => remove("tiers", option.value)} onremoveAll={() => clear("tiers")} />
    </div>
    <div class="d-flex flex-wrap gap-2 ms-auto">
        <div class="d-flex flex-column">
            <span class="form-label small text-body-secondary mb-1">Breakdown</span>
            <div class="btn-group btn-group-sm" role="group" aria-label="Breakdown">
                {#each BREAKDOWNS as breakdown (breakdown)}
                    <button type="button" class="btn btn-outline-primary text-capitalize"
                        class:active={filters.breakdown === breakdown}
                        aria-pressed={filters.breakdown === breakdown}
                        onclick={() => (filters.breakdown = breakdown)}>
                        {breakdown}
                    </button>
                {/each}
            </div>
        </div>
        <div class="d-flex flex-column">
            <span class="form-label small text-body-secondary mb-1">Granularity</span>
            <div class="btn-group btn-group-sm" role="group" aria-label="Granularity">
                {#each GRANULARITIES as granularity (granularity)}
                    <button type="button" class="btn btn-outline-primary text-capitalize"
                        class:active={filters.granularity === granularity}
                        aria-pressed={filters.granularity === granularity}
                        onclick={() => (filters.granularity = granularity)}>
                        {granularity}
                    </button>
                {/each}
            </div>
        </div>
    </div>
</div>

<style>
    .grow {
        flex: 1 1 12rem;
        min-width: 8rem;
        --sms-width: 100%;
    }

    .picker:not(.grow) {
        --sms-width: 11rem;
    }

    .picker {
        --sms-bg: var(--bs-body-bg);
        --sms-options-bg: var(--bs-body-bg);
        --sms-text-color: var(--bs-body-color);
        --sms-placeholder-color: var(--bs-body-color);
        --sms-placeholder-opacity: 1;
        --sms-border: var(--bs-border-width) solid var(--bs-border-color);
        --sms-focus-border: var(--bs-border-width) solid var(--bs-primary);
        --sms-border-radius: var(--bs-border-radius-sm);
        --sms-active-color: var(--bs-primary-bg-subtle);
        --sms-selected-bg: var(--bs-primary-bg-subtle);
        --sms-selected-text-color: var(--bs-body-color);
        --sms-min-height: calc(1.5em + 0.5rem + 2px);
        --sms-padding: 0 0.25rem;
        --sms-font-size: 0.875rem;
        --sms-options-z-index: 1060;
        --sms-options-max-height: 40vh;
        --sms-options-bg: var(--bs-body-bg);
        --sms-options-border: var(--bs-border-width) solid var(--bs-border-color);
        --sms-options-border-radius: var(--bs-border-radius);
        --sms-options-margin: 0.25rem 0 0;
        --sms-options-padding: 0.25rem;
        --sms-options-li-padding: 0.3rem 0.5rem;
        font-size: 0.875rem;
        min-width: 6rem;
    }

    .picker :global(div.multiselect > ul.options) {
        box-shadow: var(--bs-box-shadow);
        width: max-content;
        min-width: 100%;
        max-width: 28rem;
    }

    .picker :global(div.multiselect > ul.options > li) {
        white-space: nowrap;
    }

    .picker :global(div.multiselect.disabled) {
        background: var(--bs-secondary-bg);
        --sms-placeholder-color: var(--bs-secondary-color);
    }

    .picker :global(div.multiselect > ul.options > li) {
        border-radius: var(--bs-border-radius-sm);
    }

    .picker :global(div.multiselect > ul.selected > li) {
        border-radius: var(--bs-border-radius-sm);
    }

    .picker :global(div.multiselect > ul.selected > li:has(.badge)) {
        background: none;
        padding: 0;
    }

    .item {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        min-width: 0;
        max-width: 100%;
    }

    .picker :global(div.multiselect > ul.selected) {
        align-items: center;
        gap: 0.125rem;
        margin: 0;
        min-width: 0;
    }

    .picker :global(div.multiselect > ul.selected > input) {
        min-width: 0;
        width: 2em;
    }

    .picker :global(div.multiselect > ul.selected > li) {
        margin: 0;
        padding: 0 0.3rem;
        flex: 0 1 auto;
        min-width: 0;
        max-width: 100%;
    }

</style>
