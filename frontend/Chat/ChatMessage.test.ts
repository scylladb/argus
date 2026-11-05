import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import ChatMessage from "./ChatMessage.svelte";
import { splitTurns } from "./chatTree";
import { chatNode } from "./chatTestData";

const users = { u1: { id: "u1", username: "alice", full_name: "Alice Smith", picture_id: undefined } } as never;
const LONG = "Two upgrade tests failed on rc3. ".repeat(20);

const question = chatNode("q", "user", null, { content: "What failed on rc3?" });
const first = chatNode("a1", "assistant", "q", { content: "first answer" });
const call = chatNode("a2", "assistant", "q", {
    content: "", tool_calls: [{ id: "c1", name: "get_summary", arguments: "{\"version\": \"2025.1.0~rc3\"}" }],
    memory_snapshot: [{ memory_id: "m1", revision: "r1" }],
});
const result = chatNode("t", "tool", "a2", { tool_call_id: "c1", tool_name: "get_summary", content: "{\"failed\": 2}" });
const answer = chatNode("a3", "assistant", "t", { content: LONG, reasoning: "Look at rc3 only" });
const nodes = [question, first, call, result, answer];
const memories = [{ id: "m1", revision: "r1", content: "We run tests on GCE" }] as never;

const renderTurn = (props: Record<string, unknown> = {}) => {
    const onSetHead = vi.fn().mockResolvedValue(undefined);
    const [turn] = splitTurns([question, call, result, answer]);
    render(ChatMessage, { props: { turn, nodes, users, memories, onSetHead, onConfirm: vi.fn(), onDismiss: vi.fn(),
                                   ...props } });
    return { onSetHead };
};

describe("ChatMessage", () => {
    afterEach(cleanup);

    it("shows who asked and collapses the answer to a preview", async () => {
        renderTurn();

        expect(screen.getByText("Alice Smith")).toBeTruthy();
        expect(screen.getByText("What failed on rc3?")).toBeTruthy();
        const preview = screen.getByRole("button", { name: /Two upgrade tests failed/ });
        expect(preview.textContent?.endsWith("…")).toBe(true);
        expect(screen.queryByText(/Used 1 tool/)).toBeNull();

        await fireEvent.click(screen.getByRole("button", { name: "Show answer" }));

        expect(screen.getByRole("button", { name: "Collapse" })).toBeTruthy();
        expect(screen.getByText("Used 1 tool")).toBeTruthy();
        expect(screen.getByText("Reasoning")).toBeTruthy();
        expect(screen.getByText(/Context used: 1 memory/)).toBeTruthy();
        expect(screen.getByText("We run tests on GCE")).toBeTruthy();
    });

    it("switches between the answers to the same question", async () => {
        const { onSetHead } = renderTurn({ initiallyExpanded: true });

        expect(screen.getByText("2/2")).toBeTruthy();
        await fireEvent.click(screen.getByRole("button", { name: "Previous answer" }));

        expect(onSetHead).toHaveBeenCalledWith("a1");
        expect((screen.getByRole("button", { name: "Next answer" }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("names the answer after the active assistant identity", () => {
        renderTurn({ assistant: { connection: "c", name: "Argos", picture_url: "/api/v1/chat/identity/c/picture?v=1",
                                  updated_by: null, updated_at: null } });

        expect(screen.getByText("Argos")).toBeTruthy();
        expect(document.querySelector("img.rounded-circle")?.getAttribute("src")).toBe(
            "/api/v1/chat/identity/c/picture?v=1");
    });

    it("forks after a finished answer", async () => {
        const onFork = vi.fn().mockResolvedValue(undefined);
        renderTurn({ forkNode: "a3", onFork });

        await fireEvent.click(screen.getByRole("button", { name: /Fork/ }));

        expect(onFork).toHaveBeenCalledWith("a3");
    });

    it("shows a compaction's progress while it is written, and a failure after", async () => {
        const summary = chatNode("s", "summary", null, { content: "", reasoning: "hmm", status: "streaming", auto: true });
        const { rerender } = render(ChatMessage, { props: { turn: splitTurns([summary])[0], nodes: [summary], users,
                                                            memories, onSetHead: vi.fn(), onConfirm: vi.fn(),
                                                            onDismiss: vi.fn() } });

        expect(screen.getByText("Compacting")).toBeTruthy();
        expect(screen.getByText(/automatically before the next answer · thinking it over/)).toBeTruthy();
        const writing = { ...summary, content: "Two upgrade tests failed" };
        await rerender({ turn: splitTurns([writing])[0], nodes: [writing] });
        expect(screen.getByText(/4 words written/)).toBeTruthy();
        const question = chatNode("q9", "user", "s", { content: "next question" });
        const waiting = chatNode("a9", "assistant", "q9", { content: "", status: "streaming" });
        cleanup();
        render(ChatMessage, { props: { turn: splitTurns([question, waiting])[0], nodes: [writing, question, waiting],
                                       users, memories, onSetHead: vi.fn(), onConfirm: vi.fn(), onDismiss: vi.fn() } });
        expect(screen.getByText("Waiting for the compaction to finish…")).toBeTruthy();
        cleanup();
        const view = render(ChatMessage, { props: { turn: splitTurns([summary])[0], nodes: [summary], users, memories,
                                                    onSetHead: vi.fn(), onConfirm: vi.fn(), onDismiss: vi.fn() } });
        const failed = { ...summary, status: "error" as const, error: "the model is down" };
        await view.rerender({ turn: splitTurns([failed])[0], nodes: [failed] });
        expect(screen.getByText(/The automatic compaction failed/)).toBeTruthy();
        expect(screen.getByText("the model is down")).toBeTruthy();
    });

    it("sanitizes the model's markdown", () => {
        const evil = chatNode("x", "assistant", "q", { content: "<img src=x onerror=alert(1)> **bold**" });
        const [turn] = splitTurns([question, evil]);
        const { container } = render(ChatMessage, {
            props: { turn, nodes: [question, evil], users, memories: [], initiallyExpanded: true,
                     onSetHead: vi.fn(), onConfirm: vi.fn(), onDismiss: vi.fn() },
        });

        expect(container.querySelector("img[onerror]")).toBeNull();
        expect(container.querySelector("strong")?.textContent).toBe("bold");
    });
});
