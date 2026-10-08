import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/svelte";

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

import SidebarSearch from "./SidebarSearch.svelte";
import { searchPage } from "./sidebarState.svelte";

const HIT = {
    id: "t1",
    type: "test",
    name: "longevity-50gb-3days-test",
    pretty_name: null,
    release_id: "master-id",
    group_id: "g1",
    release: { id: "master-id", name: "scylla-master", pretty_name: null },
    group: { id: "g1", name: "longevity", pretty_name: "Longevity" },
};

const answerWith = (response: unknown) => {
    const fetchMock = vi.fn().mockResolvedValue({ json: () => Promise.resolve({ status: "ok", response }) });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
};

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});

describe("searchPage", () => {
    it("scopes the query to a release and labels each hit", async () => {
        const fetchMock = answerWith({ hits: [HIT], total: 31 });

        const page = await searchPage({ search: "longevity 50gb", offset: 0, limit: 30 }, "master-id");

        expect(fetchMock.mock.calls[0][0]).toBe(
            "/api/v1/planning/search?query=longevity+50gb&limit=30&offset=0&releaseId=master-id"
        );
        expect(page.options[0]).toEqual({ label: "longevity-50gb-3days-test", value: "t1", hit: HIT });
        expect(page.hasMore).toBe(true);
    });

    it("searches every release without a scope and stops at the last page", async () => {
        const fetchMock = answerWith({ hits: [HIT], total: 31 });

        const page = await searchPage({ search: "longevity", offset: 30, limit: 30 }, null);

        expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/planning/search?query=longevity&limit=30&offset=30");
        expect(page.hasMore).toBe(false);
    });

    it("sends nothing for a blank query", async () => {
        const fetchMock = answerWith({ hits: [], total: 0 });

        expect(await searchPage({ search: "  ", offset: 0, limit: 30 }, null)).toEqual({ options: [], hasMore: false });
        expect(fetchMock).not.toHaveBeenCalled();
    });
});

describe("SidebarSearch", () => {
    const scope = { id: "master-id", name: "scylla-master", pretty_name: null, enabled: true, dormant: false };
    const OTHER = { ...HIT, id: "t2", name: "longevity-50gb-azure-test" };

    const search = async (text: string) => {
        const input = document.getElementById("workspace-search") as HTMLInputElement;
        await fireEvent.focus(input);
        await fireEvent.input(input, { target: { value: text } });
        return input;
    };

    const option = (name: string) =>
        waitFor(() => screen.getByText(name, { selector: "ul.options *" }), { timeout: 2000 });

    const choose = async (element: HTMLElement) => {
        await fireEvent.mouseUp(element);
        await fireEvent.click(element);
    };

    it("stays open with its results so several hits can be picked", async () => {
        answerWith({ hits: [HIT, OTHER], total: 2 });
        const onPick = vi.fn();
        render(SidebarSearch, { props: { scope: null, onPick } });
        const input = await search("longevity");

        await choose(await option("longevity-50gb-3days-test"));
        await choose(await option("longevity-50gb-azure-test"));

        expect(onPick.mock.calls.map(([hit]) => hit.id)).toEqual(["t1", "t2"]);
        expect(input.value).toBe("longevity");
        expect(screen.getByText("longevity-50gb-3days-test", { selector: "ul.options *" })).toBeTruthy();
    });

    it("keeps its scope while open even when the sidebar moves to another release", async () => {
        const fetchMock = answerWith({ hits: [HIT], total: 1 });
        const { rerender } = render(SidebarSearch, { props: { scope, onPick: vi.fn() } });
        await search("longevity");
        await option("longevity-50gb-3days-test");

        await rerender({ scope: { ...scope, id: "other-id", name: "scylla-2025.1" } });

        expect(screen.getByText(/in scylla-master/)).toBeTruthy();
        expect(fetchMock.mock.calls.every(([url]) => String(url).includes("releaseId=master-id"))).toBe(true);
    });

    it("clears the query from the button inside the field", async () => {
        answerWith({ hits: [HIT], total: 1 });
        render(SidebarSearch, { props: { scope: null, onPick: vi.fn() } });
        expect(screen.queryByRole("button", { name: "Clear the search" })).toBeNull();
        const input = await search("longevity");

        await fireEvent.click(await waitFor(() => screen.getByRole("button", { name: "Clear the search" })));

        await waitFor(() => expect(input.value).toBe(""));
        expect(screen.queryByRole("button", { name: "Clear the search" })).toBeNull();
        expect(document.activeElement).toBe(input);
    });

    it("shows the status of a test hit and the counts of a group hit", async () => {
        const GROUP = { ...HIT, id: "g1", type: "group", name: "longevity", pretty_name: "Longevity", group_id: null, group: null };
        answerWith({ hits: [GROUP, HIT], total: 2 });
        const statsFor = (hit: { id: string }) =>
            hit.id === "t1" ? { status: "failed" } : { counts: { total: 2, failed: 1, passed: 1 } };
        render(SidebarSearch, { props: { scope, statsFor, onPick: vi.fn() } });
        await search("longevity");

        const test = (await option("longevity-50gb-3days-test")).closest("li") as HTMLElement;
        const group = (await option("Longevity")).closest("li") as HTMLElement;

        expect(test.textContent).toContain("Status: failed.");
        expect(group.querySelector("[role=img]")?.getAttribute("aria-label")).toBe("1 failed, 1 passed of 2");
    });

    it.each(["status:failed", "istatus:not", "assignee:alice"])("explains that %s needs a release", async (facet) => {
        answerWith({ hits: [], total: 0 });
        render(SidebarSearch, { props: { scope: null, onPick: vi.fn() } });
        await search(`longevity ${facet}`);

        await waitFor(() => expect(screen.getByText(/work inside one release/)).toBeTruthy(), { timeout: 2000 });
    });

    it("drops the release scope from an issue key search and explains an empty result", async () => {
        answerWith({ hits: [], total: 0 });
        render(SidebarSearch, { props: { scope, onPick: vi.fn() } });
        await search("issue:SCT-1");

        await waitFor(() => expect(screen.getByText(/No runs are linked to that issue/)).toBeTruthy(), { timeout: 2000 });
        expect(screen.queryByText(/in scylla-master/)).toBeNull();
    });

    it("keeps the release scope for a config search and explains an empty result", async () => {
        answerWith({ hits: [], total: 0 });
        render(SidebarSearch, { props: { scope, onPick: vi.fn() } });
        await search("config:backend=aws status:failed");

        await waitFor(() => expect(screen.getByText(/config: takes name=value/)).toBeTruthy(), { timeout: 2000 });
        expect(screen.getByText(/in scylla-master/)).toBeTruthy();
    });

    it("marks the hits already open in the panel", async () => {
        answerWith({ hits: [HIT, OTHER], total: 2 });
        render(SidebarSearch, { props: { scope: null, openIds: ["t1"], onPick: vi.fn() } });
        await search("longevity");

        const opened = (await option("longevity-50gb-3days-test")).closest("li") as HTMLElement;
        const other = (await option("longevity-50gb-azure-test")).closest("li") as HTMLElement;

        expect(opened.textContent).toContain("Open in the panel");
        expect(other.textContent).not.toContain("Open in the panel");
    });

    it("shows the release scope and drops it on request, keeping the focus", async () => {
        render(SidebarSearch, { props: { scope, onPick: vi.fn() } });

        expect(screen.getByText(/in scylla-master/)).toBeTruthy();
        await fireEvent.click(screen.getByRole("button", { name: "Search all releases" }));

        expect(screen.queryByText(/in scylla-master/)).toBeNull();
        await waitFor(() => expect(document.activeElement?.id).toBe("workspace-search"));
    });

    it("scopes the search again after a reset", async () => {
        const { component } = render(SidebarSearch, { props: { scope, onPick: vi.fn() } });
        await fireEvent.click(screen.getByRole("button", { name: "Search all releases" }));
        await fireEvent.keyDown(document.getElementById("workspace-search") as HTMLElement, { key: "Escape" });
        expect(screen.queryByText(/in scylla-master/)).toBeNull();

        component.resetScope();

        await waitFor(() => expect(screen.getByText(/in scylla-master/)).toBeTruthy());
    });

    it("shows why the server refused a query", async () => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
            json: () => Promise.resolve({ status: "error", response: { arguments: ["A search query holds at most 24 words and facets"] } }),
        }));
        render(SidebarSearch, { props: { scope: null, onPick: vi.fn() } });
        await search("too many words");

        await waitFor(() => expect(screen.getByText(/at most 24 words/)).toBeTruthy(), { timeout: 2000 });
    });

    it("shows no scope at the top level", () => {
        render(SidebarSearch, { props: { scope: null, onPick: vi.fn() } });

        expect(screen.queryByRole("button", { name: "Search all releases" })).toBeNull();
    });
});
