import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import ChatForks from "./ChatForks.svelte";
import { branches } from "./chatTree";
import { chatNode } from "./chatTestData";

const users = { u1: { id: "u1", username: "alice", full_name: "Alice Smith" } } as never;
const nodes = [
    chatNode("q1", "user", null, { content: "what failed?" }),
    chatNode("a1", "assistant", "q1", { content: "two tests" }),
    chatNode("q2", "user", "a1", { content: "rerun them on aws" }),
    chatNode("a2", "assistant", "q2", { content: "proposed" }),
    chatNode("f2", "user", "a1", { content: "rerun them on gce" }),
    chatNode("f2a", "assistant", "f2", { content: "proposed on gce" }),
];

describe("ChatForks", () => {
    afterEach(cleanup);

    it("lists the branches and switches to another one", async () => {
        const onSwitch = vi.fn().mockResolvedValue(undefined);
        render(ChatForks, { props: { branches: branches(nodes, "a2"), users, busy: false, onSwitch } });

        expect(screen.getByText("Current")).toBeTruthy();
        expect(screen.getByText("Asks instead: rerun them on gce")).toBeTruthy();
        await fireEvent.click(screen.getByRole("button", { name: "Switch" }));

        expect(onSwitch).toHaveBeenCalledWith("f2a");
    });

    it("explains forking while there is one branch", () => {
        render(ChatForks, { props: { branches: branches(nodes.slice(0, 4), "a2"), users, busy: false,
                                     onSwitch: vi.fn() } });

        expect(screen.getByText(/One branch so far/)).toBeTruthy();
    });
});
