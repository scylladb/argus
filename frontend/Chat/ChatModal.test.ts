import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/svelte";

vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../Common/ApiUtils", () => ({ fetchJson: vi.fn() }));
vi.mock("../Stores/UserlistSubscriber.js", () => ({
    userList: { subscribe: (fn: (v: unknown) => void) => { fn({}); return () => {}; } },
}));

import { fetchJson } from "../Common/ApiUtils";
import ChatModal from "./ChatModal.svelte";
import { chatNode } from "./chatTestData";
import type { Conversation } from "./types";

class SilentEventSource {
    onmessage = null;
    onerror = null;
    readyState = 1;
    close() {}
}

const conversation = (nodes = [chatNode("q", "user", null, { content: "what failed?" }),
                               chatNode("a", "assistant", "q", { content: "two tests" })]): Conversation => ({
    entity_id: "r1", entity_type: "release", entity_name: "scylla-2025.1", scopes: [], configured: true,
    model: { connection: "c", model: "gemma", context_window: 8000, tools: true }, head: nodes.at(-1)?.node ?? null,
    busy: null, nodes, context: { window: 8000, used: 10, last_prompt_tokens: 5, estimated_tokens: 5,
                                  messages_since_compaction: 2 },
});

describe("ChatModal", () => {
    beforeEach(() => vi.stubGlobal("EventSource", SilentEventSource));
    afterEach(() => {
        cleanup();
        vi.unstubAllGlobals();
        vi.mocked(fetchJson).mockReset();
    });

    it("lets an admin clear the chat after a confirmation", async () => {
        vi.mocked(fetchJson).mockImplementation(async (url: string, init?: RequestInit) =>
            init?.method === "DELETE" ? conversation([]) : url.endsWith("/memories") ? [] : conversation());
        render(ChatModal, { props: { entityType: "release", entityId: "r1", entityName: "scylla-2025.1", isAdmin: true,
                                     onClose: vi.fn() } });
        expect(await screen.findByText("what failed?")).toBeTruthy();

        await fireEvent.click(screen.getByRole("button", { name: /Clear chat/ }));
        await fireEvent.click(screen.getByRole("button", { name: "Clear" }));

        await waitFor(() => expect(screen.queryByText("what failed?")).toBeNull());
        expect(vi.mocked(fetchJson)).toHaveBeenCalledWith("/api/v1/chat/release/r1", expect.objectContaining({
            method: "DELETE" }));
    });

    it("shows no clear button to other users", async () => {
        vi.mocked(fetchJson).mockImplementation(async (url: string) => url.endsWith("/memories") ? [] : conversation());
        render(ChatModal, { props: { entityType: "release", entityId: "r1", entityName: "scylla-2025.1",
                                     onClose: vi.fn() } });

        expect(await screen.findByText("what failed?")).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Clear chat/ })).toBeNull();
    });
});
