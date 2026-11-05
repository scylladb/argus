import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/svelte";

vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../Common/ApiUtils", () => ({ fetchJson: vi.fn() }));

import { fetchJson } from "../Common/ApiUtils";
import ChatMemories from "./ChatMemories.svelte";
import type { Memory, Revision } from "./types";

const users = { u1: { id: "u1", username: "alice", full_name: "Alice Smith" } } as never;
const memory: Memory = {
    id: "m1", entity_id: "v1", entity_type: "release", entity_name: "scylla-2025.1", kind: "note",
    content: "We run tests on GCE", revision: "r2", created_by: "u1", created_at: "", updated_by: "u1",
    updated_at: new Date().toISOString(), source_node: null,
};
const revision: Revision = {
    revision: "r2", memory_id: "m1", entity_id: "v1", action: "update", before: "We run on AWS",
    after: "We run tests on GCE", kind: "note", before_kind: "note", user_id: "u1", source: "chat",
    source_node: "n1", reverts: null, created_at: new Date().toISOString(),
};
const scopes = [{ id: "v1", type: "view" as const, name: "Week1" },
                { id: "rel", type: "release" as const, name: "scylla-2025.1" }];

describe("ChatMemories", () => {
    afterEach(() => {
        cleanup();
        vi.mocked(fetchJson).mockReset();
    });

    it("adds a finding on the chosen release", async () => {
        const onChange = vi.fn();
        vi.mocked(fetchJson).mockResolvedValue([memory]);
        render(ChatMemories, { props: { base: "/api/v1/chat/view/v1", tab: "list", memories: [memory], scopes, users, onChange } });

        expect(screen.getByText("release scylla-2025.1", { exact: false })).toBeTruthy();
        expect(screen.getByText("Alice Smith · just now", { exact: false })).toBeTruthy();
        await fireEvent.input(screen.getByLabelText("New memory"), { target: { value: "rc3 failures are infra" } });
        await fireEvent.click(screen.getByRole("switch", { name: /Finding/ }));
        await fireEvent.change(screen.getByLabelText("Store on"), { target: { value: "rel" } });
        await fireEvent.click(screen.getByRole("button", { name: /Add/ }));

        await waitFor(() => expect(onChange).toHaveBeenCalledWith([memory]));
        const [url, init] = vi.mocked(fetchJson).mock.calls[0];
        expect(url).toBe("/api/v1/chat/view/v1/memories");
        expect(JSON.parse(init!.body as string)).toEqual({ content: "rc3 failures are infra", kind: "finding",
                                                         scope: "rel" });
    });

    it("stores on the view itself by default", async () => {
        vi.mocked(fetchJson).mockResolvedValue([memory]);
        render(ChatMemories, { props: { base: "/b", tab: "list", memories: [], scopes, users, onChange: vi.fn() } });

        expect((screen.getByLabelText("Store on") as HTMLSelectElement).value).toBe("v1");
        await fireEvent.input(screen.getByLabelText("New memory"), { target: { value: "x" } });
        await fireEvent.click(screen.getByRole("button", { name: /Add/ }));

        await waitFor(() => expect(vi.mocked(fetchJson)).toHaveBeenCalled());
        expect(JSON.parse(vi.mocked(fetchJson).mock.calls[0][1]!.body as string).scope).toBeNull();
    });

    it("shows the history and reverts a change", async () => {
        vi.mocked(fetchJson).mockImplementation(async (url: string) =>
            url.endsWith("/history") ? [revision] : url.endsWith("/revert") ? memory : [memory]);
        render(ChatMemories, { props: { base: "/b", tab: "history", memories: [memory], scopes, users, onChange: vi.fn() } });

        expect(await screen.findByText("We run on AWS")).toBeTruthy();
        expect(screen.getByText("changed", { exact: false })).toBeTruthy();

        await fireEvent.click(screen.getByRole("button", { name: "Revert this change" }));

        await waitFor(() => expect(vi.mocked(fetchJson).mock.calls.some(([url]) => url === "/b/memories/history/r2/revert"))
            .toBe(true));
    });
});
