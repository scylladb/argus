import { SvelteMap, SvelteSet } from "svelte/reactivity";
import { fetchJson } from "../../Common/ApiUtils";
import { displayName, type NamedEntity, type ReleaseSummary } from "./sidebarSort";

export const STATS_TTL = 300_000;
export const PREFETCH_DELAY = 150;
export const STATS_SLOTS = 2;
export const PINS_KEY = "argus-workspace-pinned-releases";

export interface Release extends NamedEntity {
    enabled: boolean;
    dormant: boolean;
    priority?: number | null;
}

export interface Group extends NamedEntity {
    release_id: string;
}

export interface Test extends NamedEntity {
    group_id: string;
    release_id: string;
}

export interface SearchRef extends NamedEntity {
    release_id?: string;
}

export interface SearchHit extends NamedEntity {
    type: "release" | "group" | "test" | "run";
    status?: string;
    release_id?: string;
    group_id?: string;
    test_id?: string;
    release?: SearchRef | null;
    group?: SearchRef | null;
    test?: SearchRef | null;
}

export interface Loadable<T> {
    data?: T;
    loading: boolean;
    error?: string;
}

export interface StatsEntry {
    data?: ReleaseSummary | { dormant: true };
    fetchedAt: number;
    error?: string;
    promise?: Promise<void>;
}

export type SearchOption = {
    label: string;
    value: string;
    hit: SearchHit;
};

interface SearchPageParams {
    search: string;
    offset: number;
    limit: number;
}

type Assignees = Record<string, string[]>;

const readPins = (): string[] => {
    try {
        const ids = JSON.parse(localStorage.getItem(PINS_KEY) ?? "[]");
        return Array.isArray(ids) ? ids.filter((id) => typeof id === "string") : [];
    } catch {
        return [];
    }
};

const writePins = (ids: Iterable<string>): void => {
    try {
        localStorage.setItem(PINS_KEY, JSON.stringify([...ids]));
    } catch {
        // Storage is blocked, as in a private window: the pins last for this page.
    }
};

const errorMessage = (error: unknown): string => (error instanceof Error ? error.message : String(error));

export const searchPage = async (
    { search, offset, limit }: SearchPageParams,
    releaseId: string | null
): Promise<{ options: SearchOption[]; hasMore: boolean }> => {
    if (!search.trim()) return { options: [], hasMore: false };
    const params = new URLSearchParams({ query: search, limit: String(limit), offset: String(offset) });
    if (releaseId) params.set("releaseId", releaseId);
    const { hits, total }: { hits: SearchHit[]; total: number } = await fetchJson(`/api/v1/planning/search?${params}`);
    return {
        options: hits.map((hit) => ({ label: displayName(hit), value: hit.id, hit })),
        hasMore: offset + hits.length < total,
    };
};

export class Limiter {
    #active = 0;
    #waiting: (() => void)[] = [];

    constructor(readonly slots: number) {}

    async run<T>(task: () => Promise<T>): Promise<T> {
        if (this.#active < this.slots) {
            this.#active++;
        } else {
            await new Promise<void>((resolve) => this.#waiting.push(resolve));
        }
        try {
            return await task();
        } finally {
            const next = this.#waiting.shift();
            if (next) {
                next();
            } else {
                this.#active--;
            }
        }
    }
}

export class SidebarState {
    releases: Loadable<Release[]> = $state({ loading: false });
    release: Release | null = $state(null);
    group: Group | null = $state(null);
    groups = new SvelteMap<string, Loadable<Group[]>>();
    tests = new SvelteMap<string, Loadable<Test[]>>();
    groupAssignees = new SvelteMap<string, Assignees>();
    testAssignees = new SvelteMap<string, Assignees>();
    stats = new SvelteMap<string, StatsEntry>();
    pinned = new SvelteSet<string>(readPins());
    #limiter = new Limiter(STATS_SLOTS);
    #prefetch: { name: string; timer: ReturnType<typeof setTimeout> } | null = null;

    async loadReleases(): Promise<void> {
        this.releases = { data: this.releases.data, loading: true };
        try {
            this.releases = { data: await fetchJson("/api/v1/releases"), loading: false };
        } catch (error) {
            this.releases = { data: this.releases.data, loading: false, error: errorMessage(error) };
        }
    }

    async #load<T>(cache: SvelteMap<string, Loadable<T>>, key: string, url: string, force: boolean) {
        const current = cache.get(key);
        if (current?.loading || (current?.data && !force)) return;
        cache.set(key, { data: current?.data, loading: true });
        try {
            cache.set(key, { data: await fetchJson(url), loading: false });
        } catch (error) {
            cache.set(key, { data: current?.data, loading: false, error: errorMessage(error) });
        }
    }

    async #loadAssignees(cache: SvelteMap<string, Assignees>, key: string, url: string, force: boolean) {
        if (cache.has(key) && !force) return;
        try {
            cache.set(key, await fetchJson(url));
        } catch {
            cache.set(key, {});
        }
    }

    loadGroups(release: Release, { force = false } = {}): Promise<unknown> {
        const params = new URLSearchParams({ releaseId: release.id });
        return Promise.all([
            this.#load(this.groups, release.id, `/api/v1/groups?${params}`, force),
            this.#loadAssignees(this.groupAssignees, release.id, `/api/v1/release/assignees/groups?${params}`, force),
        ]);
    }

    loadTests(group: Group, { force = false } = {}): Promise<unknown> {
        const params = new URLSearchParams({ groupId: group.id });
        return Promise.all([
            this.#load(this.tests, group.id, `/api/v1/tests?${params}`, force),
            this.#loadAssignees(this.testAssignees, group.id, `/api/v1/release/assignees/tests?${params}`, force),
        ]);
    }

    ensureStats(release: Release, { force = false } = {}): Promise<void> {
        if (release.dormant) return Promise.resolve();
        const entry = this.stats.get(release.name);
        if (entry?.promise) return entry.promise;
        if (!force && entry?.data && Date.now() - entry.fetchedAt < STATS_TTL) return Promise.resolve();
        const promise = this.#fetchStats(release, force);
        this.stats.set(release.name, { data: entry?.data, fetchedAt: entry?.fetchedAt ?? 0, promise });
        return promise;
    }

    async #fetchStats(release: Release, force: boolean): Promise<void> {
        const params = new URLSearchParams({ release: release.name, force: force ? "1" : "0" });
        try {
            const data: StatsEntry["data"] = await fetchJson(`/api/v1/release/stats/summary?${params}`);
            this.stats.set(release.name, { data, fetchedAt: Date.now() });
        } catch (error) {
            const entry = this.stats.get(release.name);
            this.stats.set(release.name, {
                data: entry?.data,
                fetchedAt: entry?.fetchedAt ?? 0,
                error: errorMessage(error),
            });
        }
    }

    summary(release: Release | null): ReleaseSummary | undefined {
        const data = release ? this.stats.get(release.name)?.data : undefined;
        return data && !("dormant" in data) ? data : undefined;
    }

    loadEager(): Promise<unknown> {
        const eager = (this.releases.data ?? []).filter(
            (release) => this.pinned.has(release.id) || (release.priority ?? 0) > 0
        );
        return Promise.all(eager.map((release) => this.#limiter.run(() => this.ensureStats(release))));
    }

    togglePin(release: Release): void {
        if (this.pinned.has(release.id)) {
            this.pinned.delete(release.id);
        } else {
            this.pinned.add(release.id);
            this.#limiter.run(() => this.ensureStats(release));
        }
        writePins(this.pinned);
    }

    prefetch(release: Release): void {
        if (release.dormant || this.#prefetch?.name === release.name) return;
        this.cancelPrefetch();
        const timer = setTimeout(() => {
            this.#prefetch = null;
            this.#limiter.run(() => this.ensureStats(release));
        }, PREFETCH_DELAY);
        this.#prefetch = { name: release.name, timer };
    }

    cancelPrefetch(): void {
        if (this.#prefetch) clearTimeout(this.#prefetch.timer);
        this.#prefetch = null;
    }

    enterRelease(release: Release): void {
        this.release = release;
        this.group = null;
        this.loadGroups(release);
        this.ensureStats(release);
    }

    enterGroup(group: Group, release: Release): void {
        this.release = release;
        this.group = group;
        this.loadTests(group);
        this.loadGroups(release);
        this.ensureStats(release);
    }

    up(): void {
        if (this.group) {
            this.group = null;
        } else {
            this.release = null;
        }
    }

    showReleases(): void {
        this.release = null;
        this.group = null;
    }

    #releaseFor(id: string | undefined, fallback?: SearchRef | null): Release | undefined {
        const known = this.releases.data?.find((release) => release.id === id);
        if (known) return known;
        if (!fallback) return undefined;
        return { enabled: true, dormant: false, ...fallback } as Release;
    }

    locate(hit: SearchHit): string | null {
        switch (hit.type) {
        case "release": {
            const release = this.#releaseFor(hit.id, hit);
            if (release) this.enterRelease(release);
            return null;
        }
        case "group": {
            const release = this.#releaseFor(hit.release_id, hit.release);
            if (release) this.enterGroup({ ...hit, release_id: release.id }, release);
            return null;
        }
        case "test":
        case "run": {
            const releaseId = hit.release_id ?? hit.release?.id;
            const groupRef = hit.group;
            const release = this.#releaseFor(releaseId, hit.release);
            if (!release || !groupRef) return null;
            this.enterGroup({ id: groupRef.id, name: groupRef.name, pretty_name: groupRef.pretty_name, release_id: release.id }, release);
            return hit.type === "test" ? hit.id : (hit.test_id ?? hit.test?.id ?? null);
        }
        }
    }
}
