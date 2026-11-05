import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/svelte";

vi.mock("../Stores/AlertStore", () => ({ sendMessage: vi.fn() }));
vi.mock("../Common/ApiUtils", () => ({ fetchJson: vi.fn() }));

import { fetchJson } from "../Common/ApiUtils";
import ChatMcpManager from "./ChatMcpManager.svelte";

const server = (tools: { name: string; description: string; mode: string }[] = []) => ({
    name: "jira", url: "https://mcp.test/mcp", transport: "streamable_http", enabled: true,
    headers: ["Authorization"], tools, probed_at: tools.length ? new Date().toISOString() : null,
});
const TOOLS = [{ name: "read_status", description: "Read an issue's status.", mode: "off" }];

describe("ChatMcpManager", () => {
    afterEach(() => {
        cleanup();
        vi.mocked(fetchJson).mockReset();
    });

    it("probes a server, lists its tools, and switches a tool's mode", async () => {
        vi.mocked(fetchJson).mockImplementation(async (url: string, init?: RequestInit) => {
            if (url.endsWith("/probe")) return server(TOOLS);
            if (url.endsWith("/tools")) {
                const modes = JSON.parse(init!.body as string).modes;
                return server(TOOLS.map((tool) => ({ ...tool, mode: modes[tool.name] ?? tool.mode })));
            }
            return [server()];
        });
        render(ChatMcpManager);

        await fireEvent.click(await screen.findByRole("button", { name: /Probe/ }));
        const row = (await screen.findByText("read_status")).closest("tr") as HTMLElement;
        await fireEvent.click(within(row).getByRole("button", { name: "Direct" }));

        const call = vi.mocked(fetchJson).mock.calls.find(([url]) => url.endsWith("/tools"))!;
        expect(JSON.parse(call[1]!.body as string)).toEqual({ modes: { read_status: "direct" } });
        expect(within(row).getByRole("button", { name: "Direct" }).getAttribute("aria-pressed")).toBe("true");
    });

    it("shows header names and never their values, and keeps them unless replaced", async () => {
        vi.mocked(fetchJson).mockResolvedValue([server()]);
        render(ChatMcpManager);

        expect(await screen.findByText("Authorization")).toBeTruthy();
        await fireEvent.click(screen.getByRole("button", { name: "Edit jira" }));
        await fireEvent.click(screen.getByRole("button", { name: "Save" }));

        const call = vi.mocked(fetchJson).mock.calls.find(([url, init]) => url.endsWith("/server") && init?.method === "POST")!;
        expect(JSON.parse(call[1]!.body as string).headers).toBeNull();
    });
});
