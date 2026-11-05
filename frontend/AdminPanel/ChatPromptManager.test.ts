import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";

vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../Common/ApiUtils", () => ({ fetchJson: vi.fn() }));

import { fetchJson } from "../Common/ApiUtils";
import ChatPromptManager from "./ChatPromptManager.svelte";

const DEFAULT = "You are the assistant.\n{tool_rules}\n{scope}\n{memories}\n{summary}";
const info = (template: string, edited: boolean) => ({
    template, default: DEFAULT, edited, placeholders: ["tool_rules", "scope", "memories", "summary", "skills"],
    required: ["tool_rules", "scope", "memories", "summary"], updated_by: null, updated_at: null,
});

describe("ChatPromptManager", () => {
    afterEach(() => {
        cleanup();
        vi.mocked(fetchJson).mockReset();
    });

    it("shows the server's template error, and resets to the default", async () => {
        vi.mocked(fetchJson).mockImplementation(async (url: string, init?: RequestInit) => {
            if (url.endsWith("/skills")) return [];
            if (init?.method === "PUT") throw new Error("The system prompt must keep {memories}");
            if (init?.method === "DELETE") return info(DEFAULT, false);
            return info("Edited.\n{tool_rules}\n{scope}\n{memories}\n{summary}", true);
        });
        render(ChatPromptManager);

        const textarea = (await screen.findByLabelText("System prompt")) as HTMLTextAreaElement;
        await fireEvent.input(textarea, { target: { value: "{tool_rules}" } });
        await fireEvent.click(screen.getAllByRole("button", { name: "Save" })[0]);
        expect(await screen.findByText("The system prompt must keep {memories}")).toBeTruthy();

        await fireEvent.click(screen.getByRole("button", { name: /Reset to default/ }));
        await vi.waitFor(() => expect(textarea.value).toBe(DEFAULT));
        expect(screen.getByText("Default")).toBeTruthy();
    });

    it("saves a skill with its mode", async () => {
        const skill = { name: "triage", description: "How to triage", content: "Read the events first.",
                        mode: "on_demand", updated_at: null };
        let saved = false;
        vi.mocked(fetchJson).mockImplementation(async (url: string, init?: RequestInit) => {
            if (url.endsWith("/skill")) {
                saved = true;
                return skill;
            }
            if (url.endsWith("/skills")) return saved ? [skill] : [];
            return info(DEFAULT, false);
        });
        render(ChatPromptManager);

        await fireEvent.click(await screen.findByRole("button", { name: /Add skill/ }));
        await fireEvent.input(screen.getByLabelText("Name"), { target: { value: "triage" } });
        await fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "on_demand" } });
        await fireEvent.input(screen.getByLabelText("Description"), { target: { value: "How to triage" } });
        await fireEvent.input(screen.getByLabelText("Text"), { target: { value: "Read the events first." } });
        await fireEvent.submit(screen.getByLabelText("Text").closest("form")!);

        const call = vi.mocked(fetchJson).mock.calls.find(([url]) => url.endsWith("/skill"))!;
        expect(JSON.parse(call[1]!.body as string)).toEqual({ name: "triage", description: "How to triage",
                                                            content: "Read the events first.", mode: "on_demand" });
        expect(await screen.findByText("On demand")).toBeTruthy();
    });
});
