import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/svelte";

vi.mock("../Common/ApiUtils", () => ({ fetchJson: vi.fn() }));
vi.mock("../argus.js", () => ({ applicationCurrentUser: { roles: ["ROLE_USER"] } }));
vi.mock("../Stores/UserlistSubscriber.js", () => ({
    userList: {
        subscribe: (fn: (v: unknown) => void) => {
            fn({ u1: { id: "u1", username: "alice", full_name: "Alice Smith" } });
            return () => {};
        },
    },
}));

import { fetchJson } from "../Common/ApiUtils";
import ChatAnchor from "./ChatAnchor.svelte";

describe("ChatAnchor", () => {
    afterEach(cleanup);

    it("says when no model is configured", async () => {
        vi.mocked(fetchJson).mockResolvedValue({ configured: false, messages: 0, last: null });
        render(ChatAnchor, { props: { dashboardObject: { id: "r1", name: "scylla-2025.1" },
                                      dashboardObjectType: "release" } });

        expect(await screen.findByText("No chat model is configured yet")).toBeTruthy();
        expect(vi.mocked(fetchJson)).toHaveBeenCalledWith("/api/v1/chat/release/r1/meta");
    });

    it("shows the count and the last asker", async () => {
        vi.mocked(fetchJson).mockResolvedValue({ configured: true, messages: 3,
                                                 last: { user_id: "u1", at: new Date().toISOString() } });
        render(ChatAnchor, { props: { dashboardObject: { id: "v1", display_name: "Week1" } } });

        expect(await screen.findByText(/3 questions · last by Alice Smith just now/)).toBeTruthy();
        expect(vi.mocked(fetchJson)).toHaveBeenCalledWith("/api/v1/chat/view/v1/meta");
    });
});
