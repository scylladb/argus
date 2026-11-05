import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import ChatComposer from "./ChatComposer.svelte";

const props = (extra: Record<string, unknown> = {}) => ({
    entityType: "release", busy: false, canRetry: true, canUndo: true,
    onSend: vi.fn().mockResolvedValue(true), onStop: vi.fn(), onRetry: vi.fn(), onUndo: vi.fn(), ...extra,
});

describe("ChatComposer", () => {
    afterEach(() => {
        cleanup();
        sessionStorage.clear();
    });

    it("sends the question with Auto mode, and remembers the choice in the tab", async () => {
        const first = props();
        render(ChatComposer, { props: first });

        await fireEvent.click(screen.getByRole("switch", { name: "Auto mode" }));
        await fireEvent.input(screen.getByLabelText("Question"), { target: { value: "start week1" } });
        await fireEvent.click(screen.getByRole("button", { name: /Send/ }));
        await fireEvent.click(screen.getByRole("button", { name: /Try again/ }));

        expect(first.onSend).toHaveBeenCalledWith("start week1", true);
        expect(first.onRetry).toHaveBeenCalledWith(true);
        cleanup();
        render(ChatComposer, { props: props() });
        expect((screen.getByRole("switch", { name: "Auto mode" }) as HTMLInputElement).checked).toBe(true);
    });

    it("sends without Auto mode by default", async () => {
        const fresh = props();
        render(ChatComposer, { props: fresh });

        await fireEvent.input(screen.getByLabelText("Question"), { target: { value: "hello" } });
        await fireEvent.click(screen.getByRole("button", { name: /Send/ }));

        expect(fresh.onSend).toHaveBeenCalledWith("hello", false);
    });
});
