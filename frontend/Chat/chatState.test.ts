import { describe, expect, it } from "vitest";
import { applyEvent } from "./chatState";
import type { ChatNode, Conversation } from "./types";

const answer: ChatNode = {
    node: "a", parent: "q", role: "assistant", content: "", reasoning: null, user_id: "u", tool_calls: [],
    tool_call_id: null, tool_name: null, action: null, model_name: "m", usage: null, memory_snapshot: [],
    status: "streaming", error: null, hidden: false, created_at: "", updated_at: "",
};

const conversation = (): Conversation => ({
    entity_id: "e", entity_type: "release", entity_name: "r", scopes: [], configured: true, model: null, head: "a", busy: null,
    nodes: [answer], context: { window: 100, used: 0, last_prompt_tokens: null, estimated_tokens: 0,
                                messages_since_compaction: 0 },
});

describe("applyEvent", () => {
    it("appends deltas, then a node replaces them", () => {
        let state = applyEvent(conversation(), { type: "delta", node: "a", content: "Hel", reasoning: "" });
        state = applyEvent(state, { type: "delta", node: "a", content: "lo", reasoning: "think" });
        expect(state.nodes[0].content).toBe("Hello");
        expect(state.nodes[0].reasoning).toBe("think");

        state = applyEvent(state, { type: "node", node: { ...answer, content: "Hello!", status: "done" } });
        expect(state.nodes[0].content).toBe("Hello!");
        expect(state.nodes[0].status).toBe("done");
    });

    it("adds a new node and updates head, busy and context from a state event", () => {
        let state = applyEvent(conversation(), { type: "node", node: { ...answer, node: "b", parent: "a" } });
        state = applyEvent(state, {
            type: "state", head: "b", busy: { node: "b", user_id: "u", since: "" },
            context: { window: 100, used: 40, last_prompt_tokens: 30, estimated_tokens: 10, messages_since_compaction: 2 },
        });
        expect(state.nodes.map((n) => n.node)).toEqual(["a", "b"]);
        expect(state.head).toBe("b");
        expect(state.busy?.node).toBe("b");
        expect(state.context.used).toBe(40);
    });

    it("replaces everything on a snapshot and ignores a delta for an unknown node", () => {
        const fresh = { ...conversation(), head: null, nodes: [] };
        let state = applyEvent(conversation(), { type: "snapshot", conversation: fresh });
        state = applyEvent(state, { type: "delta", node: "zzz", content: "x", reasoning: "" });
        expect(state).toEqual(fresh);
    });
});
