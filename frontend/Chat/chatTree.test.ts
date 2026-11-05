import { describe, expect, it } from "vitest";
import { activePath, alternativesOf, atForkPoint, branches, splitTurns } from "./chatTree";
import type { ChatNode } from "./types";

let clock = 0;
const node = (id: string, role: ChatNode["role"], parent: string | null, extra: Partial<ChatNode> = {}): ChatNode => ({
    node: id, parent, role, content: id, reasoning: null, user_id: "u1", tool_calls: [], tool_call_id: null,
    tool_name: null, action: null, model_name: null, usage: null, memory_snapshot: [], status: "done", error: null,
    hidden: false, created_at: new Date(2030, 0, 1, 0, 0, clock++).toISOString(), updated_at: "", ...extra,
});

const q1 = node("q1", "user", null);
const a1 = node("a1", "assistant", "q1");
const a1b = node("a1b", "assistant", "q1");
const q2 = node("q2", "user", "a1b");
const call = node("call", "assistant", "q2", { tool_calls: [{ id: "c", name: "get_summary", arguments: "{}" }] });
const result = node("result", "tool", "call", { tool_call_id: "c", tool_name: "get_summary" });
const answer = node("answer", "assistant", "result");
const gone = node("gone", "assistant", "q1", { hidden: true });
const nodes = [q1, a1, a1b, q2, call, result, answer, gone];

describe("activePath", () => {
    it("walks from head to the root", () => {
        expect(activePath(nodes, "answer").map((n) => n.node)).toEqual(["q1", "a1b", "q2", "call", "result", "answer"]);
    });

    it("is empty without a head", () => {
        expect(activePath(nodes, null)).toEqual([]);
    });
});

describe("alternativesOf", () => {
    it("lists the visible answers to the same question, oldest first", () => {
        const { siblings, index } = alternativesOf(nodes, a1b);
        expect(siblings.map((n) => n.node)).toEqual(["a1", "a1b"]);
        expect(index).toBe(1);
    });
});

describe("splitTurns", () => {
    it("groups each question with what followed it", () => {
        const turns = splitTurns(activePath(nodes, "answer"));
        expect(turns.map((turn) => turn.opener.node)).toEqual(["q1", "q2"]);
        expect(turns[1].answers.map((n) => n.node)).toEqual(["call", "answer"]);
        expect(turns[1].tools.map((n) => n.node)).toEqual(["result"]);
        expect(turns[1].firstAnswer?.node).toBe("call");
    });
});

describe("branches", () => {
    const root = node("r1", "user", null);
    const answer = node("r1a", "assistant", "r1");
    const later = node("r2", "user", "r1a");
    const laterAnswer = node("r2a", "assistant", "r2");
    const fork = node("f2", "user", "r1a", { content: "a different follow-up" });
    const forkAnswer = node("f2a", "assistant", "f2");
    const retry = node("r2b", "assistant", "r2");
    const undone = node("u2", "user", "r1a", { hidden: true });
    const all = [root, answer, later, laterAnswer, fork, forkAnswer, retry, undone];

    it("lists one branch per visible leaf, newest first, with where it parts", () => {
        const listed = branches(all, "r2a");

        expect(listed.map((branch) => branch.leaf.node)).toEqual(["r2b", "f2a", "r2a"]);
        expect(listed[2].current).toBe(true);
        expect(listed[2].divergence).toBeNull();
        expect(listed[1].divergence).toMatchObject({ kind: "question", node: { node: "f2" } });
        expect(listed[0].divergence).toMatchObject({ kind: "answer", question: { node: "r2" } });
        expect(listed[1].questions).toBe(2);
    });

    it("knows a fork point from the end of a branch", () => {
        expect(atForkPoint(all, "r1a")).toBe(true);
        expect(atForkPoint(all, "r2a")).toBe(false);
    });
});
