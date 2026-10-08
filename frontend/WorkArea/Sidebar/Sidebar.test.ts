import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, waitFor, fireEvent } from "@testing-library/svelte";

vi.hoisted(() => {
    window.matchMedia = (query: string) =>
        ({
            matches: false,
            media: query,
            onchange: null,
            addEventListener: () => {},
            removeEventListener: () => {},
            addListener: () => {},
            removeListener: () => {},
            dispatchEvent: () => false,
        }) as unknown as MediaQueryList;
});

vi.mock("../../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../../Stores/UserlistSubscriber", () => ({
    userList: {
        subscribe: (fn: (v: unknown) => void) => {
            fn({});
            return () => {};
        },
    },
}));

import Sidebar from "./Sidebar.svelte";

const MASTER = { id: "master-id", name: "scylla-master", pretty_name: null, enabled: true, dormant: false, priority: 10 };
const OLD = { id: "old-id", name: "scylla-2025.1", pretty_name: null, enabled: true, dormant: false, priority: 0 };
const GROUPS = [
    { id: "g1", name: "longevity", pretty_name: "Longevity", release_id: MASTER.id },
    { id: "g2", name: "core-qa", pretty_name: "Core QA", release_id: MASTER.id },
    { id: "g3", name: "core-qa-2", pretty_name: "Core QA", release_id: MASTER.id },
];
const TESTS = [
    { id: "t1", name: "alpha-test", pretty_name: null, group_id: "g1", release_id: MASTER.id },
    { id: "t2", name: "beta-test", pretty_name: null, group_id: "g1", release_id: MASTER.id },
];
const SUMMARY = {
    total: 2,
    passed: 1,
    failed: 1,
    to_investigate: 1,
    groups: {
        g1: {
            total: 2,
            passed: 1,
            failed: 1,
            to_investigate: 1,
            tests: {
                t1: { status: "passed", investigation_status: "not_investigated", start_time: "2026-10-01T10:00:00.000Z" },
                t2: { status: "failed", investigation_status: "not_investigated", start_time: null },
            },
        },
    },
};

const ok = (response: unknown) => Promise.resolve({ json: () => Promise.resolve({ status: "ok", response }) });

const serve = ({ stats = () => ok(SUMMARY) }: { stats?: () => Promise<unknown> } = {}) => {
    const fetchMock = vi.fn((url: string) => {
        if (url === "/api/v1/releases") return ok([MASTER, OLD]);
        if (url.startsWith("/api/v1/release/stats/summary")) return stats();
        if (url.startsWith("/api/v1/groups")) return ok(GROUPS);
        if (url.startsWith("/api/v1/tests")) return ok(TESTS);
        if (url.startsWith("/api/v1/release/assignees")) return ok({});
        return Promise.reject(new Error(`unexpected ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
};

const renderSidebar = (props: Record<string, unknown> = {}) => {
    const callbacks = {
        onToggleTest: vi.fn(),
        onOpenTest: vi.fn(),
        onOpenTests: vi.fn(),
        onOpenRun: vi.fn(),
        onCloseRun: vi.fn(),
    };
    render(Sidebar, { props: { ...callbacks, ...props } });
    return callbacks;
};

const row = (name: string) =>
    screen.getByText(name, { selector: ".sidebar-row .row-name" }).closest("button") as HTMLButtonElement;

const rowNames = () =>
    [...document.querySelectorAll(".sidebar-row")].map((button) => button.querySelector(".row-name")?.textContent);

const breadcrumb = () => screen.getByRole("navigation", { name: "breadcrumb" }).textContent?.replace(/\s+/g, " ").trim();

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
});

describe("Sidebar", () => {
    it("lists the releases in server order and fetches stats for the prioritized one", async () => {
        const fetchMock = serve();
        renderSidebar();

        await waitFor(() => expect(rowNames()).toEqual(["scylla-master", "scylla-2025.1"]));
        await waitFor(() =>
            expect(fetchMock).toHaveBeenCalledWith("/api/v1/release/stats/summary?release=scylla-master&force=0", undefined)
        );
        expect(fetchMock.mock.calls.some(([url]) => url.includes("release=scylla-2025.1"))).toBe(false);
    });

    it("lists a pinned release above the others and keeps the pin", async () => {
        serve();
        renderSidebar();
        await waitFor(() => expect(rowNames()).toEqual(["scylla-master", "scylla-2025.1"]));

        const pin = screen.getByRole("button", { name: "Pin scylla-2025.1 to the top" });
        expect(pin.getAttribute("aria-pressed")).toBe("false");
        await fireEvent.click(pin);

        await waitFor(() => expect(rowNames()).toEqual(["scylla-2025.1", "scylla-master"]));
        expect(pin.getAttribute("aria-pressed")).toBe("true");

        cleanup();
        renderSidebar();
        await waitFor(() => expect(rowNames()).toEqual(["scylla-2025.1", "scylla-master"]));
    });

    it("swaps the list for the groups of a clicked release and shows the breadcrumb", async () => {
        serve();
        renderSidebar();

        await fireEvent.click(await waitFor(() => row("scylla-master")));

        await waitFor(() => expect(rowNames()).toEqual(["Longevity", "Core QA", "Core QA"]));
        expect(breadcrumb()).toBe("Releases scylla-master");
    });

    it("tells apart groups that share a display name", async () => {
        serve();
        renderSidebar();

        await fireEvent.click(await waitFor(() => row("scylla-master")));

        await waitFor(() => expect(screen.getByText("core-qa-2")).toBeTruthy());
        expect(screen.getByText("core-qa")).toBeTruthy();
        expect(screen.queryByText("longevity")).toBeNull();
    });

    it("moves with the arrow keys and returns to the row it came from", async () => {
        serve();
        renderSidebar();

        const master = await waitFor(() => row("scylla-master"));
        master.focus();
        await fireEvent.keyDown(master, { key: "ArrowDown" });
        await waitFor(() => expect(document.activeElement).toBe(row("scylla-2025.1")));

        await fireEvent.keyDown(row("scylla-2025.1"), { key: "ArrowUp" });
        await waitFor(() => expect(document.activeElement).toBe(row("scylla-master")));

        await fireEvent.keyDown(row("scylla-master"), { key: "ArrowRight" });
        await waitFor(() => expect(document.activeElement).toBe(row("Longevity")));

        await fireEvent.keyDown(row("Longevity"), { key: "ArrowLeft" });
        await waitFor(() => expect(document.activeElement).toBe(row("scylla-master")));
        expect(breadcrumb()).toBe("Releases");
    });

    it("lists the groups when going up from a group found by search", async () => {
        const fetchMock = serve();
        const searchHit = { hits: [{ id: "t1", type: "test", name: "alpha-test", pretty_name: null, release_id: MASTER.id, group_id: "g1", release: MASTER, group: GROUPS[0] }], total: 1 };
        const base = fetchMock.getMockImplementation()!;
        fetchMock.mockImplementation((url: string) => (url.startsWith("/api/v1/planning/search") ? ok(searchHit) : base(url)));
        const { onOpenTest } = renderSidebar();
        await waitFor(() => row("scylla-master"));

        const input = document.getElementById("workspace-search") as HTMLInputElement;
        await fireEvent.focus(input);
        await fireEvent.input(input, { target: { value: "alpha" } });
        const option = await waitFor(() => screen.getByText("alpha-test", { selector: "ul.options *" }), { timeout: 2000 });
        await fireEvent.mouseUp(option);
        await fireEvent.click(option);
        await waitFor(() => expect(onOpenTest).toHaveBeenCalledWith("t1"));
        await waitFor(() => expect(breadcrumb()).toBe("Releases scylla-master Longevity"));
        await waitFor(() => expect(row("alpha-test").getAttribute("tabindex")).toBe("0"));
        expect(document.activeElement).toBe(input);

        await fireEvent.keyDown(await waitFor(() => row("alpha-test")), { key: "ArrowLeft" });

        await waitFor(() => expect(rowNames()).toEqual(["Longevity", "Core QA", "Core QA"]));
        await waitFor(() => expect(document.activeElement).toBe(row("Longevity")));
    });

    it("closes an open test when it is picked again in the search", async () => {
        const fetchMock = serve();
        const searchHit = { hits: [{ id: "t1", type: "test", name: "alpha-test", pretty_name: null, release_id: MASTER.id, group_id: "g1", release: MASTER, group: GROUPS[0] }], total: 1 };
        const base = fetchMock.getMockImplementation()!;
        fetchMock.mockImplementation((url: string) => (url.startsWith("/api/v1/planning/search") ? ok(searchHit) : base(url)));
        const { onToggleTest, onOpenTest } = renderSidebar({ openTests: ["t1"] });
        await waitFor(() => row("scylla-master"));

        const input = document.getElementById("workspace-search") as HTMLInputElement;
        await fireEvent.focus(input);
        await fireEvent.input(input, { target: { value: "alpha" } });
        const option = await waitFor(() => screen.getByText("alpha-test", { selector: "ul.options *" }), { timeout: 2000 });
        await fireEvent.mouseUp(option);
        await fireEvent.click(option);

        expect(onToggleTest).toHaveBeenCalledWith("t1");
        expect(onOpenTest).not.toHaveBeenCalled();
        expect(breadcrumb()).toBe("Releases");
    });

    it("closes an open run when its hit is picked again in the search", async () => {
        const fetchMock = serve();
        const runHit = {
            id: "r1", type: "run", name: "alpha-test#3", pretty_name: null, status: "failed", test_id: "t1",
            release_id: MASTER.id, group_id: "g1", release: MASTER, group: GROUPS[0], test: { id: "t1", name: "alpha-test" },
        };
        const base = fetchMock.getMockImplementation()!;
        fetchMock.mockImplementation((url: string) =>
            url.startsWith("/api/v1/planning/search") ? ok({ hits: [runHit], total: 1 }) : base(url));
        const { onOpenRun, onCloseRun } = renderSidebar({ openTests: ["t1"], openRuns: { t1: ["r1"] } });
        await waitFor(() => row("scylla-master"));

        const input = document.getElementById("workspace-search") as HTMLInputElement;
        await fireEvent.focus(input);
        await fireEvent.input(input, { target: { value: "issue:SCT-1" } });
        const option = await waitFor(() => screen.getByText("alpha-test#3", { selector: "ul.options *" }), { timeout: 2000 });
        expect(option.closest("li")?.textContent).toContain("pick it again to close it");
        await fireEvent.mouseUp(option);
        await fireEvent.click(option);

        expect(onCloseRun).toHaveBeenCalledWith("t1", "r1");
        expect(onOpenRun).not.toHaveBeenCalled();
    });

    it("shows the loaded status of a test in the search results", async () => {
        const fetchMock = serve();
        const searchHit = { hits: [{ id: "t2", type: "test", name: "beta-test", pretty_name: null, release_id: MASTER.id, group_id: "g1", release: MASTER, group: GROUPS[0] }], total: 1 };
        const base = fetchMock.getMockImplementation()!;
        fetchMock.mockImplementation((url: string) => (url.startsWith("/api/v1/planning/search") ? ok(searchHit) : base(url)));
        renderSidebar();
        await fireEvent.click(await waitFor(() => row("scylla-master")));
        await waitFor(() => expect(rowNames()).toEqual(["Longevity", "Core QA", "Core QA"]));

        const input = document.getElementById("workspace-search") as HTMLInputElement;
        await fireEvent.focus(input);
        await fireEvent.input(input, { target: { value: "beta" } });
        const option = await waitFor(() => screen.getByText("beta-test", { selector: "ul.options *" }), { timeout: 2000 });

        expect(option.closest("li")?.textContent).toContain("Status: failed.");
    });

    it("goes back up through the breadcrumb", async () => {
        serve();
        renderSidebar();

        await fireEvent.click(await waitFor(() => row("scylla-master")));
        await fireEvent.click(await waitFor(() => row("Longevity")));
        await waitFor(() => expect(breadcrumb()).toBe("Releases scylla-master Longevity"));

        await fireEvent.click(screen.getByRole("button", { name: "scylla-master" }));
        await waitFor(() => expect(breadcrumb()).toBe("Releases scylla-master"));

        await fireEvent.click(screen.getByRole("button", { name: "Releases" }));
        await waitFor(() => expect(breadcrumb()).toBe("Releases"));
    });

    it("re-sorts the tests by status when the stats arrive", async () => {
        let release: (value: unknown) => void = () => {};
        serve({ stats: () => new Promise((resolve) => (release = resolve)).then(() => ok(SUMMARY)) });
        renderSidebar();

        await fireEvent.click(await waitFor(() => row("scylla-master")));
        await fireEvent.click(await waitFor(() => row("Longevity")));
        await waitFor(() => expect(rowNames()).toEqual(["alpha-test", "beta-test"]));

        release(null);

        await waitFor(() => expect(rowNames()).toEqual(["beta-test", "alpha-test"]));
    });

    it("shows the last run date only for tests that ran", async () => {
        serve();
        renderSidebar();

        await fireEvent.click(await waitFor(() => row("scylla-master")));
        await fireEvent.click(await waitFor(() => row("Longevity")));

        await waitFor(() => expect(row("alpha-test").textContent).toContain("2026-10-01 10:00"));
        expect(row("beta-test").textContent).not.toMatch(/\d{4}-\d{2}-\d{2}/);
    });

    it("toggles a test and marks the open ones", async () => {
        serve();
        const { onToggleTest } = renderSidebar({ openTests: ["t1"] });

        await fireEvent.click(await waitFor(() => row("scylla-master")));
        await fireEvent.click(await waitFor(() => row("Longevity")));
        await waitFor(() => expect(row("alpha-test")).toBeTruthy());

        expect(row("alpha-test").getAttribute("aria-pressed")).toBe("true");
        expect(row("beta-test").getAttribute("aria-pressed")).toBe("false");
        await fireEvent.click(row("beta-test"));
        expect(onToggleTest).toHaveBeenCalledWith("t2");
    });

    it("opens every test of the group", async () => {
        serve();
        const { onOpenTests } = renderSidebar();

        await fireEvent.click(await waitFor(() => row("scylla-master")));
        await fireEvent.click(await waitFor(() => row("Longevity")));
        await waitFor(() => expect(row("alpha-test")).toBeTruthy());

        await fireEvent.click(screen.getByRole("button", { name: "Open all tests" }));
        expect(onOpenTests).toHaveBeenCalledWith(["t2", "t1"]);
    });

    it("shows an error with a retry when the groups fail to load", async () => {
        const fetchMock = serve();
        fetchMock.mockImplementation((url: string) => {
            if (url === "/api/v1/releases") return ok([MASTER]);
            if (url.startsWith("/api/v1/groups")) return Promise.reject(new Error("boom"));
            return ok({});
        });
        renderSidebar();

        await fireEvent.click(await waitFor(() => row("scylla-master")));

        await waitFor(() => expect(screen.getByText(/Couldn't load this list: boom/)).toBeTruthy());
        expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    });

    it("focuses the search on / but not while typing in a text area", async () => {
        serve();
        renderSidebar();
        await waitFor(() => row("scylla-master"));
        const searchInput = document.getElementById("workspace-search") as HTMLInputElement;
        const textarea = document.body.appendChild(document.createElement("textarea"));
        textarea.focus();

        await fireEvent.keyDown(textarea, { key: "/" });
        expect(document.activeElement).toBe(textarea);

        textarea.blur();
        await fireEvent.keyDown(document.body, { key: "/" });
        expect(document.activeElement).toBe(searchInput);
        textarea.remove();
    });
});
