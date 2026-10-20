import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import NemesisDetails from "./NemesisDetails.svelte";
import type { NemesisInfo, NemesisResource } from "./types";

const T0 = Date.UTC(2026, 9, 20, 10, 0, 0) / 1000;

const nemesis = (overrides: Partial<NemesisInfo> = {}): NemesisInfo => ({
    class_name: "DisruptRestartNodeMonkey",
    name: "disrupt_restart_node",
    description: "Restart (hard) the target node.\n\nWaits for the node to rejoin.",
    duration: 90,
    target_node: { name: "db-node-1", ip: "1.2.3.4", shards: 8 },
    status: "succeeded",
    start_time: T0,
    end_time: T0 + 90,
    stack_trace: "",
    ...overrides,
});

const resource: NemesisResource = { name: "db-node-1", state: "running", instance_info: { private_ip: "10.0.0.5" } };

const withClipboard = () => {
    const writeText = vi.fn();
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    return writeText;
};

afterEach(() => {
    cleanup();
    delete (navigator as { clipboard?: unknown }).clipboard;
});

describe("NemesisDetails", () => {
    it("shows the class, name, status and duration", () => {
        render(NemesisDetails, { props: { nemesis: nemesis(), resource } });

        expect(screen.getByText("DisruptRestartNodeMonkey")).toBeTruthy();
        expect(screen.getByText("disrupt_restart_node")).toBeTruthy();
        expect(screen.getByText("Succeeded")).toBeTruthy();
        expect(screen.getByText("1 minute, 30 seconds")).toBeTruthy();
    });

    it("hides the duration when it is zero", () => {
        render(NemesisDetails, { props: { nemesis: nemesis({ duration: 0 }), resource } });

        expect(screen.queryByText("Duration")).toBeNull();
    });

    it("shows the target node with its private IP and state from the resources", () => {
        render(NemesisDetails, { props: { nemesis: nemesis(), resource } });

        expect(screen.getByText("db-node-1")).toBeTruthy();
        expect(screen.getByText("1.2.3.4")).toBeTruthy();
        expect(screen.getByText("10.0.0.5")).toBeTruthy();
        expect(screen.getByText("running")).toBeTruthy();
        expect(screen.getByText("8")).toBeTruthy();
    });

    it("shows not found when the node is missing from the resources", () => {
        render(NemesisDetails, { props: { nemesis: nemesis() } });

        expect(screen.getAllByText("not found")).toHaveLength(2);
    });

    it("renders the description with its line breaks", () => {
        const { container } = render(NemesisDetails, { props: { nemesis: nemesis(), resource } });

        expect(screen.getByText("Description")).toBeTruthy();
        expect(container.querySelector(".description")?.textContent).toContain("node.\n\nWaits");
    });

    it("omits the description block when there is none", () => {
        render(NemesisDetails, { props: { nemesis: nemesis({ description: null }), resource } });

        expect(screen.queryByText("Description")).toBeNull();
    });

    it("labels the reason by status", () => {
        const { unmount } = render(NemesisDetails, {
            props: { nemesis: nemesis({ status: "skipped", stack_trace: "Not supported" }), resource },
        });
        expect(screen.getByText("Skip reason")).toBeTruthy();
        expect(screen.getByText("Not supported")).toBeTruthy();
        unmount();

        render(NemesisDetails, { props: { nemesis: nemesis({ status: "failed", stack_trace: "Traceback: boom" }), resource } });
        expect(screen.getByText("Failure reason")).toBeTruthy();
        expect(screen.getByText("Traceback: boom")).toBeTruthy();
        cleanup();

        render(NemesisDetails, { props: { nemesis: nemesis({ status: "succeeded", stack_trace: "done" }), resource } });
        expect(screen.getByText("Message")).toBeTruthy();
    });

    it("renders no reason without a message", () => {
        render(NemesisDetails, { props: { nemesis: nemesis({ status: "failed", stack_trace: "" }), resource } });

        expect(screen.queryByText("Failure reason")).toBeNull();
    });

    it("copies the reason to the clipboard", async () => {
        const writeText = withClipboard();
        render(NemesisDetails, { props: { nemesis: nemesis({ status: "failed", stack_trace: "Traceback: boom" }), resource } });

        await fireEvent.click(screen.getByRole("button", { name: /Copy/ }));

        expect(writeText).toHaveBeenCalledWith("Traceback: boom");
    });

    it("offers no copy button when the clipboard is unavailable", () => {
        render(NemesisDetails, { props: { nemesis: nemesis({ status: "failed", stack_trace: "Traceback: boom" }), resource } });

        expect(screen.queryByRole("button", { name: /Copy/ })).toBeNull();
    });
});
