import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/svelte";
import ChatActionCard from "./ChatActionCard.svelte";
import { chatNode, showRunAction, startAction, zeusAction, zeusReportAction } from "./chatTestData";
import type { ChatAction } from "./types";

const users = { u1: { id: "u1", username: "alice", full_name: "Alice Smith" } } as never;

describe("ChatActionCard", () => {
    afterEach(cleanup);

    it("lists what would start and what was left out, and runs on confirm", async () => {
        const onConfirm = vi.fn().mockResolvedValue(undefined);
        const onDismiss = vi.fn().mockResolvedValue(undefined);
        render(ChatActionCard, { props: { node: chatNode("card", "action", "a", { action: startAction() }), users,
                                          onConfirm, onDismiss } });

        expect(screen.getByText("Start 1 test")).toBeTruthy();
        expect(screen.getByText("backend=gce")).toBeTruthy();
        expect(screen.getByText(/gce is not a choice of backend/)).toBeTruthy();
        await fireEvent.click(screen.getByRole("button", { name: "All parameters" }));
        expect(screen.getByText("scylla_version")).toBeTruthy();

        await fireEvent.click(screen.getByRole("button", { name: /Run/ }));
        expect(onConfirm).toHaveBeenCalledWith("card");
        await fireEvent.click(screen.getByRole("button", { name: /Dismiss/ }));
        expect(onDismiss).toHaveBeenCalledWith("card");
    });

    it("links each started run and names who confirmed", () => {
        const action = startAction({
            state: "done", confirmed_by: "u1", confirmed_at: new Date().toISOString(),
            results: [{ build_system_id: "scylla-2025.1/upgrades/rolling_upgrade", test: "upgrades/rolling_upgrade",
                        queue_item: 7, build_number: 42, error: null }],
        });
        render(ChatActionCard, { props: { node: chatNode("card", "action", "a", { action }), users,
                                          onConfirm: vi.fn(), onDismiss: vi.fn() } });

        const link = screen.getByRole("link", { name: "Run #42" }) as HTMLAnchorElement;
        expect(link.getAttribute("href")).toBe("/test/scylla-2025.1/upgrades/rolling_upgrade/42");
        expect(screen.getByText(/Confirmed by Alice Smith/)).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Run/ })).toBeNull();
    });
});


describe("ChatActionCard for Zeus", () => {
    afterEach(() => {
        cleanup();
        vi.useRealTimers();
    });

    it("lists the runs and the question, and queues on confirm", async () => {
        const onConfirm = vi.fn().mockResolvedValue(undefined);
        render(ChatActionCard, { props: { node: chatNode("card", "action", "a", { action: zeusAction() }), users,
                                          onConfirm, onDismiss: vi.fn(), onRefresh: vi.fn() } });

        expect(screen.getByText("Queue 1 Zeus investigation")).toBeTruthy();
        expect(screen.getByText("upgrades/rolling_upgrade")).toBeTruthy();
        expect(screen.getByText(/Why did the upgrade fail\?/)).toBeTruthy();
        await fireEvent.click(screen.getByRole("button", { name: /Queue/ }));
        expect(onConfirm).toHaveBeenCalledWith("card");
    });

    it("refreshes while a task is open and shows the report once completed", async () => {
        vi.useFakeTimers();
        const onRefresh = vi.fn().mockResolvedValue(undefined);
        const open = zeusAction({ state: "done", confirmed_by: "u1", results: [
            { run_id: "r1", test: "upgrades/rolling_upgrade", task_id: "t1", status: "processing", response: null,
              error: null }] });
        const { rerender } = render(ChatActionCard, { props: {
            node: chatNode("card", "action", "a", { action: open }), users, onConfirm: vi.fn(), onDismiss: vi.fn(),
            onRefresh } });

        expect(screen.getByText("processing")).toBeTruthy();
        await vi.advanceTimersByTimeAsync(30_000);
        expect(onRefresh).toHaveBeenCalledWith("card");

        const done = zeusAction({ state: "done", confirmed_by: "u1", results: [
            { run_id: "r1", test: "upgrades/rolling_upgrade", task_id: "t1", status: "completed",
              response: "**Root cause**: the AMI never booted.", error: null }] });
        await rerender({ node: chatNode("card", "action", "a", { action: done }), users, onConfirm: vi.fn(),
                         onDismiss: vi.fn(), onRefresh });
        onRefresh.mockClear();
        await fireEvent.click(screen.getByText("Zeus report"));
        await vi.advanceTimersByTimeAsync(60_000);

        expect(screen.getByText("completed")).toBeTruthy();
        expect(screen.getByText("Root cause").tagName).toBe("STRONG");
        expect(onRefresh).not.toHaveBeenCalled();
    });
});


describe("ChatActionCard for a shown run", () => {
    afterEach(cleanup);

    it("opens the run in a new tab and asks for nothing", () => {
        render(ChatActionCard, { props: { node: chatNode("card", "action", "a", { action: showRunAction(),
                                                                                  action_state: "done" } as never),
                                          users, onConfirm: vi.fn(), onDismiss: vi.fn() } });

        const link = screen.getByRole("link", { name: /Open run/ }) as HTMLAnchorElement;
        expect(link.getAttribute("href")).toBe("/test/scylla-2025.1/upgrades/rolling_upgrade/11");
        expect(link.getAttribute("target")).toBe("_blank");
        expect(screen.getByText("upgrades/rolling_upgrade")).toBeTruthy();
        expect(screen.getByText(/#11/)).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Run|Dismiss/ })).toBeNull();
        expect(screen.queryByText("Done")).toBeNull();
    });
});


describe("ChatActionCard for a Zeus report", () => {
    afterEach(cleanup);

    it("renders the whole report with its author and a link to the run", () => {
        render(ChatActionCard, { props: { node: chatNode("card", "action", "a", { action: zeusReportAction() }),
                                          users, onConfirm: vi.fn(), onDismiss: vi.fn() } });

        expect(screen.getByText(/Zeus report/)).toBeTruthy();
        expect(screen.getByText(/Zeus · just now/)).toBeTruthy();
        expect(screen.getByText("Root cause").tagName).toBe("STRONG");
        const link = screen.getByRole("link", { name: /Open run/ }) as HTMLAnchorElement;
        expect(link.getAttribute("href")).toBe("/test/scylla-2025.1/rolling-upgrade/rolling-upgrade-centos9-test/11");
        expect(screen.queryByRole("button", { name: /Run|Dismiss/ })).toBeNull();
    });
});

describe("ChatActionCard edits and new cards", () => {
    afterEach(cleanup);

    const withFields = () => startAction({
        rejected: [],
        proposal: {
            tests: [{
                test_id: "t1", test: "upgrades/rolling_upgrade", name: "rolling_upgrade", group: "upgrades",
                build_system_id: "scylla-2025.1/upgrades/rolling_upgrade", seed: "last_build", build_number: null,
                params: { backend: "aws", region: "eu-west-1", scylla_version: "2025.1.0" }, overrides: {},
                fields: [
                    { name: "backend", value: "aws", group: "environment", choices: ["aws", "gce"] },
                    { name: "region", value: "eu-west-1", group: "environment", choices: ["eu-west-1", "us-west-2"] },
                    { name: "scylla_version", value: "2025.1.0", group: "scylla" },
                ],
            }],
        },
    });

    it("edits a pending start's parameters and shows a rejection", async () => {
        const onAdjust = vi.fn().mockResolvedValueOnce("mars-1 is not a supported region").mockResolvedValueOnce(null);
        render(ChatActionCard, { props: { node: chatNode("card", "action", "a", { action: withFields() }), users,
                                          onConfirm: vi.fn(), onDismiss: vi.fn(), onAdjust } });

        await fireEvent.click(screen.getByRole("button", { name: /Edit parameters/ }));
        expect(screen.getByText("Environment")).toBeTruthy();
        await fireEvent.change(screen.getByLabelText("region"), { target: { value: "us-west-2" } });
        await fireEvent.click(screen.getByRole("button", { name: "Save" }));

        expect(onAdjust).toHaveBeenCalledWith("card", "t1", { region: "us-west-2" });
        expect(await screen.findByText("mars-1 is not a supported region")).toBeTruthy();
        await fireEvent.click(screen.getByRole("button", { name: "Save" }));
        await vi.waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).toBeNull());
    });

    it("lists a plan edit's changes and applies it", async () => {
        const onConfirm = vi.fn().mockResolvedValue(undefined);
        const action: ChatAction = {
            kind: "edit_plan", state: "pending", rejected: [], confirmed_by: null, confirmed_at: null,
            dismissed_by: null, results: [],
            proposal: { plan: "Week plan", summary: ["+ upgrades/rolling_upgrade", "labels of upgrades/x: week1 (were none)"] },
        };
        render(ChatActionCard, { props: { node: chatNode("card", "action", "a", { action }), users, onConfirm,
                                          onDismiss: vi.fn() } });

        expect(screen.getByText("Edit the plan Week plan")).toBeTruthy();
        expect(screen.getByText("+ upgrades/rolling_upgrade")).toBeTruthy();
        await fireEvent.click(screen.getByRole("button", { name: /Apply/ }));
        expect(onConfirm).toHaveBeenCalledWith("card");
    });

    it("shows an MCP call's arguments, its result, and an automatic confirmation", () => {
        const action: ChatAction = {
            kind: "mcp_call", state: "done", rejected: [], confirmed_by: "u1",
            confirmed_at: new Date().toISOString(), dismissed_by: null, auto: true,
            proposal: { server: "jira", tool: "close_issue", arguments: { key: "SCYLLA-1" } },
            results: [{ server: "jira", tool: "close_issue", text: "closed", error: null }],
        };
        render(ChatActionCard, { props: { node: chatNode("card", "action", "a", { action }), users,
                                          onConfirm: vi.fn(), onDismiss: vi.fn() } });

        expect(screen.getByText("Call close_issue on jira")).toBeTruthy();
        expect(screen.getByText(/"key": "SCYLLA-1"/)).toBeTruthy();
        expect(screen.getByText("closed")).toBeTruthy();
        expect(screen.getByText(/Confirmed automatically for Alice Smith/)).toBeTruthy();
    });
});
