import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { HIDDEN_KEY, PINS_KEY, STATS_TTL, SidebarState, type Release } from "./sidebarState.svelte";

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

    it("refreshes with force after a plain request already in flight", async () => {
        const first = deferred();
        const fetchMock = vi.fn()
            .mockImplementationOnce(() => first.promise.then(() => ok(SUMMARY)))
            .mockResolvedValue(ok(SUMMARY));
        vi.stubGlobal("fetch", fetchMock);
        const state = new SidebarState();
        const master = release("scylla-master");

        const prefetch = state.ensureStats(master);
        const refresh = state.ensureStats(master, { force: true });
        first.resolve(null);
        await Promise.all([prefetch, refresh]);

        expect(statsCalls(fetchMock)).toEqual([
            "/api/v1/release/stats/summary?release=scylla-master&force=0",
            "/api/v1/release/stats/summary?release=scylla-master&force=1",
        ]);
    });

    it("sends one forced request for two refreshes during a plain one", async () => {
        const first = deferred();
        const fetchMock = vi.fn()
            .mockImplementationOnce(() => first.promise.then(() => ok(SUMMARY)))
            .mockResolvedValue(ok(SUMMARY));
        vi.stubGlobal("fetch", fetchMock);
        const state = new SidebarState();
        const master = release("scylla-master");

        const prefetch = state.ensureStats(master);
        const refreshes = [state.ensureStats(master, { force: true }), state.ensureStats(master, { force: true })];
        first.resolve(null);
        await Promise.all([prefetch, ...refreshes]);

        expect(statsCalls(fetchMock).filter((url) => url.endsWith("force=1"))).toHaveLength(1);
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
});

describe("SidebarState hidden releases", () => {
    it("keeps the hidden releases in the browser across page loads", () => {
        const old = release("scylla-2025.1");

        new SidebarState().toggleHidden(old);

        expect(JSON.parse(localStorage.getItem(HIDDEN_KEY) ?? "[]")).toEqual([old.id]);
        expect(new SidebarState().hidden.has(old.id)).toBe(true);
    });

    it("unhides a hidden release", () => {
        const old = release("scylla-2025.1");
        const state = new SidebarState();

        state.toggleHidden(old);
        state.toggleHidden(old);

        expect(state.hidden.has(old.id)).toBe(false);
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
