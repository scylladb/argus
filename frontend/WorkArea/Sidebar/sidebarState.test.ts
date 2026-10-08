import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { Limiter, PINS_KEY, PREFETCH_DELAY, STATS_TTL, SidebarState, type Release } from "./sidebarState.svelte";

const release = (name: string, extra: Partial<Release> = {}): Release => ({
    id: `${name}-id`,
    name,
    pretty_name: null,
    enabled: true,
    dormant: false,
    priority: 0,
    ...extra,
});

const SUMMARY = { total: 1, passed: 1, to_investigate: 0, groups: {} };

const ok = (response: unknown) => ({ json: () => Promise.resolve({ status: "ok", response }) });

const deferred = () => {
    let resolve: (value: unknown) => void = () => {};
    const promise = new Promise((r) => (resolve = r));
    return { promise, resolve };
};

const statsCalls = (fetchMock: ReturnType<typeof vi.fn>) =>
    fetchMock.mock.calls.map(([url]) => url as string).filter((url) => url.startsWith("/api/v1/release/stats/summary"));

beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    localStorage.clear();
});

describe("SidebarState.ensureStats", () => {
    it("sends one request for concurrent calls", async () => {
        const fetchMock = vi.fn().mockResolvedValue(ok(SUMMARY));
        vi.stubGlobal("fetch", fetchMock);
        const state = new SidebarState();
        const master = release("scylla-master");

        await Promise.all([state.ensureStats(master), state.ensureStats(master)]);

        expect(statsCalls(fetchMock)).toEqual(["/api/v1/release/stats/summary?release=scylla-master&force=0"]);
        expect(state.summary(master)).toEqual(SUMMARY);
    });

    it("serves a fresh entry from the cache and refetches once it expires", async () => {
        const fetchMock = vi.fn().mockResolvedValue(ok(SUMMARY));
        vi.stubGlobal("fetch", fetchMock);
        const state = new SidebarState();
        const master = release("scylla-master");

        await state.ensureStats(master);
        await state.ensureStats(master);
        expect(statsCalls(fetchMock)).toHaveLength(1);

        vi.advanceTimersByTime(STATS_TTL + 1);
        await state.ensureStats(master);
        expect(statsCalls(fetchMock)).toHaveLength(2);
    });

    it("bypasses the cache and the server snapshot when forced", async () => {
        const fetchMock = vi.fn().mockResolvedValue(ok(SUMMARY));
        vi.stubGlobal("fetch", fetchMock);
        const state = new SidebarState();
        const master = release("scylla-master");

        await state.ensureStats(master);
        await state.ensureStats(master, { force: true });

        expect(statsCalls(fetchMock)[1]).toBe("/api/v1/release/stats/summary?release=scylla-master&force=1");
    });

    it("requests nothing for a dormant release", async () => {
        const fetchMock = vi.fn();
        vi.stubGlobal("fetch", fetchMock);
        const state = new SidebarState();

        await state.ensureStats(release("scylla-5.2", { dormant: true }));

        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("records a failure without leaving a request pending", async () => {
        const fetchMock = vi.fn().mockRejectedValue(new Error("network down"));
        vi.stubGlobal("fetch", fetchMock);
        const state = new SidebarState();
        const master = release("scylla-master");

        await state.ensureStats(master);

        const entry = state.stats.get("scylla-master");
        expect(entry?.error).toBe("network down");
        expect(entry?.promise).toBeUndefined();
    });
});

describe("SidebarState prefetch", () => {
    it("fetches eagerly only the releases with a priority", async () => {
        const fetchMock = vi.fn().mockResolvedValue(ok(SUMMARY));
        vi.stubGlobal("fetch", fetchMock);
        const state = new SidebarState();
        state.releases = {
            loading: false,
            data: [release("scylla-master", { priority: 10 }), release("scylla-2025.1"), release("scylla-staging", { priority: 5 })],
        };

        await state.loadEager();

        expect(statsCalls(fetchMock)).toEqual([
            "/api/v1/release/stats/summary?release=scylla-master&force=0",
            "/api/v1/release/stats/summary?release=scylla-staging&force=0",
        ]);
    });

    it("fetches only the release the pointer rests on", async () => {
        const fetchMock = vi.fn().mockResolvedValue(ok(SUMMARY));
        vi.stubGlobal("fetch", fetchMock);
        const state = new SidebarState();

        state.prefetch(release("scylla-2025.4"));
        vi.advanceTimersByTime(PREFETCH_DELAY - 1);
        state.prefetch(release("scylla-2026.1"));
        await vi.advanceTimersByTimeAsync(PREFETCH_DELAY);

        expect(statsCalls(fetchMock)).toEqual(["/api/v1/release/stats/summary?release=scylla-2026.1&force=0"]);
    });

    it("fetches nothing once the pointer leaves before the delay", async () => {
        const fetchMock = vi.fn().mockResolvedValue(ok(SUMMARY));
        vi.stubGlobal("fetch", fetchMock);
        const state = new SidebarState();

        state.prefetch(release("scylla-2026.1"));
        vi.advanceTimersByTime(PREFETCH_DELAY - 1);
        state.cancelPrefetch();
        await vi.advanceTimersByTimeAsync(PREFETCH_DELAY);

        expect(statsCalls(fetchMock)).toEqual([]);
    });
});

describe("SidebarState pins", () => {
    it("keeps the pins in the browser across page loads", () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(SUMMARY)));
        const old = release("scylla-2025.1");

        new SidebarState().togglePin(old);

        expect(JSON.parse(localStorage.getItem(PINS_KEY) ?? "[]")).toEqual([old.id]);
        expect(new SidebarState().pinned.has(old.id)).toBe(true);
    });

    it("unpins a pinned release", () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(SUMMARY)));
        const old = release("scylla-2025.1");
        const state = new SidebarState();

        state.togglePin(old);
        state.togglePin(old);

        expect(state.pinned.has(old.id)).toBe(false);
        expect(JSON.parse(localStorage.getItem(PINS_KEY) ?? "[]")).toEqual([]);
    });

    it("still pins for the page when the browser blocks storage", () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok(SUMMARY)));
        vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
            throw new Error("blocked");
        });
        vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
            throw new Error("blocked");
        });
        const old = release("scylla-2025.1");
        const state = new SidebarState();

        state.togglePin(old);

        expect(state.pinned.has(old.id)).toBe(true);
    });

    it("fetches the stats of pinned releases eagerly", async () => {
        const fetchMock = vi.fn().mockResolvedValue(ok(SUMMARY));
        vi.stubGlobal("fetch", fetchMock);
        localStorage.setItem(PINS_KEY, JSON.stringify(["scylla-2025.1-id"]));
        const state = new SidebarState();
        state.releases = { loading: false, data: [release("scylla-master"), release("scylla-2025.1")] };

        await state.loadEager();

        expect(statsCalls(fetchMock)).toEqual(["/api/v1/release/stats/summary?release=scylla-2025.1&force=0"]);
    });
});

describe("Limiter", () => {
    it("runs at most its slot count at once", async () => {
        const limiter = new Limiter(2);
        const gates = [deferred(), deferred(), deferred(), deferred()];
        let running = 0;
        let peak = 0;
        const runs = gates.map((gate) =>
            limiter.run(async () => {
                running++;
                peak = Math.max(peak, running);
                await gate.promise;
                running--;
            })
        );

        await Promise.resolve();
        expect(running).toBe(2);
        gates.forEach((gate) => gate.resolve(null));
        await Promise.all(runs);

        expect(peak).toBe(2);
    });
});

describe("SidebarState.locate", () => {
    const master = release("scylla-master");
    const group = { id: "group-id", name: "longevity", pretty_name: "Longevity", enabled: true };

    const located = () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok([])));
        const state = new SidebarState();
        state.releases = { loading: false, data: [master] };
        return state;
    };

    it("enters a release", () => {
        const state = located();

        expect(state.locate({ type: "release", id: master.id, name: master.name })).toBeNull();
        expect(state.release?.id).toBe(master.id);
        expect(state.group).toBeNull();
    });

    it("enters a group", () => {
        const state = located();

        state.locate({ type: "group", ...group, release_id: master.id, release: master });

        expect(state.release?.id).toBe(master.id);
        expect(state.group?.id).toBe("group-id");
    });

    it("enters the group of a test and returns the test", () => {
        const state = located();

        const testId = state.locate({ type: "test", id: "test-id", name: "t", release_id: master.id, group_id: group.id, group, release: master });

        expect(testId).toBe("test-id");
        expect(state.group?.id).toBe("group-id");
    });

    it("enters the group of a run and returns its test", () => {
        const state = located();

        const testId = state.locate({
            type: "run",
            id: "run-id",
            name: "t#3",
            test_id: "test-id",
            release_id: master.id,
            group,
            release: master,
        });

        expect(testId).toBe("test-id");
        expect(state.group?.id).toBe("group-id");
    });
});
