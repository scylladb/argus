import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/svelte";

vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../argus", () => ({ applicationCurrentUser: { roles: [] } }));

import ReleasePlanCreator from "./ReleasePlanCreator.svelte";

const RELEASE = { id: "r1", name: "2025.1" };

const plan = () => ({
    id: "p1",
    name: "week plan",
    description: "the weekly tests",
    owner: "u1",
    participants: [],
    target_version: "2025.1",
    release_id: "r1",
    view_id: null,
    tests: ["t1", "t2"],
    groups: [],
    assignee_mapping: {},
    options: '{"t1": {"labels": ["week1"]}}',
});

const RESPONSES: Record<string, unknown> = {
    "/api/v1/users": { u1: { id: "u1", username: "alice" } },
    "/api/v1/views/all": [],
    "/api/v1/planning/plan/p1/resolve_entities": [
        { type: "test", id: "t1", name: "test-one" },
        { type: "test", id: "t2", name: "test-two" },
    ],
    "/api/v1/release/r1/versions": [],
    "/api/v1/planning/plan/update": {},
    "/api/v1/planning/plan/create": {},
};

let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
    fetchSpy = vi.fn((url: string) =>
        Promise.resolve({
            status: 200,
            json: () => Promise.resolve({ status: "ok", response: RESPONSES[url.split("?")[0]] ?? {} }),
        }),
    );
    vi.stubGlobal("fetch", fetchSpy);
});

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});

function sentBody(url: string) {
    const call = fetchSpy.mock.calls.find(([called]) => called === url);
    return call ? JSON.parse(call[1].body) : undefined;
}

describe("ReleasePlanCreator labels", () => {
    it("shows the labels of each item and saves an added one", async () => {
        render(ReleasePlanCreator, { props: { release: RELEASE, mode: "edit", plan: plan() } });
        const input = await screen.findByLabelText("New label for test-two");
        expect(screen.getByLabelText("Remove label week1 from test-one")).toBeTruthy();

        await fireEvent.input(input, { target: { value: "sanity" } });
        await fireEvent.keyDown(input, { key: "Enter" });
        await fireEvent.click(screen.getByRole("button", { name: "Edit" }));

        await waitFor(() => expect(sentBody("/api/v1/planning/plan/update")).toBeDefined());
        const diff = sentBody("/api/v1/planning/plan/update");
        expect(diff.options_set).toEqual({ t2: { labels: ["sanity"] } });
        expect(diff.options_remove).toEqual([]);
    });

    it("refuses a label the item already carries", async () => {
        render(ReleasePlanCreator, { props: { release: RELEASE, mode: "edit", plan: plan() } });
        const input = await screen.findByLabelText("New label for test-one");

        await fireEvent.input(input, { target: { value: "WEEK1" } });
        await fireEvent.keyDown(input, { key: "Enter" });

        expect((await screen.findByRole("alert")).textContent).toContain("already there");
    });

    it("keeps the labels when a plan is created from this one", async () => {
        render(ReleasePlanCreator, { props: { release: RELEASE, mode: "createFrom", plan: plan() } });
        await screen.findByLabelText("New label for test-one");

        await fireEvent.click(screen.getByRole("button", { name: "Create" }));

        await waitFor(() => expect(sentBody("/api/v1/planning/plan/create")).toBeDefined());
        expect(sentBody("/api/v1/planning/plan/create").options).toEqual({ t1: { labels: ["week1"] } });
    });

    it("filters the items by label", async () => {
        render(ReleasePlanCreator, { props: { release: RELEASE, mode: "edit", plan: plan() } });
        await screen.findByLabelText("New label for test-two");

        await fireEvent.click(screen.getByRole("button", { name: /week1/, pressed: false }));

        expect(screen.queryByLabelText("New label for test-two")).toBeNull();
        expect(screen.getByLabelText("New label for test-one")).toBeTruthy();
    });
});
