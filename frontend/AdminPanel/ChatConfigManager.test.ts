import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/svelte";

vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../Common/ApiUtils", () => ({ fetchJson: vi.fn() }));

import { fetchJson } from "../Common/ApiUtils";
import ChatConfigManager from "./ChatConfigManager.svelte";

const connections = [
    { name: "yaml-webui", endpoint: "https://yaml.test/api", source: "config", token_set: true, token_readable: true,
      updated_by: null, updated_at: null },
    { name: "db-webui", endpoint: "https://db.test/api", source: "database", token_set: true, token_readable: true,
      updated_by: "u1", updated_at: "2030-01-01T00:00:00Z" },
];
const models = [
    { id: "Gemma-4-12B-it-GGUF", name: "Gemma-4-12B-it-GGUF", context_window: 65536, tools: true, vision: true },
    { id: "Gemma-3-4b-it-GGUF", name: "Gemma-3-4b-it-GGUF", context_window: 65536, tools: false, vision: true },
    { id: "deepseek-flash", name: "deepseek-flash", context_window: null, tools: null, vision: null },
];

const identities = [
    { connection: "db-webui", name: "Argos", picture_url: "/api/v1/chat/identity/db-webui/picture?v=1",
      updated_by: "u1", updated_at: "2030-01-01T00:00:00Z" },
];

const api = () =>
    vi.mocked(fetchJson).mockImplementation(async (url: string, init?: RequestInit) => {
        if (url.endsWith("/connections")) return { connections, default: null, identities, active_identity: null };
        if (url.endsWith("/identity/active")) return identities[0];
        if (url.endsWith("/models")) return models;
        if (url.endsWith("/test_tools")) return { tools: true, detail: "The model called the get_time tool",
                                                  latency_ms: 812 };
        if (url.endsWith("/default")) return { ...JSON.parse(init!.body as string), set_by: "u1", set_at: null };
        return {};
    });

describe("ChatConfigManager", () => {
    afterEach(() => {
        cleanup();
        vi.mocked(fetchJson).mockReset();
    });

    it("lists both sources and edits only database connections, without the token", async () => {
        api();
        render(ChatConfigManager);

        expect(await screen.findByText("yaml-webui")).toBeTruthy();
        expect(screen.getByText("argus_web.yaml")).toBeTruthy();
        expect(screen.queryByRole("button", { name: "Edit yaml-webui" })).toBeNull();

        await fireEvent.click(screen.getByRole("button", { name: "Edit db-webui" }));

        expect((screen.getByLabelText("Token") as HTMLInputElement).value).toBe("");
        expect((screen.getByLabelText("Endpoint") as HTMLInputElement).value).toBe("https://db.test/api");
    });

    it("probes the models and sets the chosen one as default", async () => {
        api();
        render(ChatConfigManager);
        await fireEvent.click(await screen.findByRole("button", { name: "Change default model" }));

        const row = (await screen.findByText("deepseek-flash")).closest("tr") as HTMLElement;
        expect(within(row).getByText("tool-calling ?")).toBeTruthy();
        await fireEvent.click(within(row).getByRole("button", { name: /Test/ }));
        expect(await within(row).findByText(/works · 812 ms/)).toBeTruthy();

        await fireEvent.click(screen.getByLabelText("Choose Gemma-3-4b-it-GGUF"));
        expect(screen.getByText(/Without tool calling/)).toBeTruthy();
        await fireEvent.click(screen.getByLabelText("Choose Gemma-4-12B-it-GGUF"));
        await fireEvent.click(screen.getByRole("button", { name: "Set Gemma-4-12B-it-GGUF as default" }));

        await waitFor(() => expect(screen.getByText("Gemma-4-12B-it-GGUF", { selector: ".fw-semibold" })).toBeTruthy());
        const call = vi.mocked(fetchJson).mock.calls.find(([url]) => url.endsWith("/default"))!;
        expect(JSON.parse(call[1]!.body as string)).toEqual({ connection: "yaml-webui", model: "Gemma-4-12B-it-GGUF",
                                                             context_window: 65536, tools: true, vision: true });
    });

    it("shows each connection's identity and makes one active", async () => {
        api();
        render(ChatConfigManager);

        expect(await screen.findByText("Argos")).toBeTruthy();
        await fireEvent.click(screen.getByRole("button", { name: "Use this identity" }));

        expect(await screen.findByText("Active identity")).toBeTruthy();
        const call = vi.mocked(fetchJson).mock.calls.find(([url]) => url.endsWith("/identity/active"))!;
        expect(JSON.parse(call[1]!.body as string)).toEqual({ connection: "db-webui" });
    });

    it("saves an identity name from the editor", async () => {
        api();
        render(ChatConfigManager);
        await fireEvent.click(await screen.findByRole("button", { name: "Identity of yaml-webui" }));

        await fireEvent.input(screen.getByLabelText("Name"), { target: { value: "Hermes" } });
        await fireEvent.click(screen.getByRole("button", { name: "Save" }));

        await waitFor(() => expect(vi.mocked(fetchJson).mock.calls.some(([url]) => url.endsWith(
            "/connection/yaml-webui/identity"))).toBe(true));
        const call = vi.mocked(fetchJson).mock.calls.find(([url]) => url.endsWith("/connection/yaml-webui/identity"))!;
        const form = call[1]!.body as FormData;
        expect(form.get("assistant_name")).toBe("Hermes");
        expect(form.get("picture")).toBeNull();
    });
});
