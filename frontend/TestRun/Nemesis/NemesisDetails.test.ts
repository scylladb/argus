import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";

const value = (label: string) => (screen.getByLabelText(label) as HTMLInputElement).value;
import NemesisDetails from "./NemesisDetails.svelte";
import type { NemesisInfo, NemesisResource } from "./types";

const T0 = Date.UTC(2026, 9, 20, 10, 0, 0) / 1000;

const nemesis = (overrides: Partial<NemesisInfo> = {}): NemesisInfo => ({
    class_name: "DisruptRestartNodeMonkey",
    name: "disrupt_restart_node",
    description_digest: "digest-1",
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
    it("shows the class, name, status and duration as labelled fields", () => {
        render(NemesisDetails, { props: { nemesis: nemesis(), resource } });

        expect(value("Class")).toBe("DisruptRestartNodeMonkey");
        expect((screen.getAllByLabelText("Name")[0] as HTMLInputElement).value).toBe("disrupt_restart_node");
        expect(screen.getByText("Succeeded")).toBeTruthy();
        expect(value("Duration")).toBe("1 minute, 30 seconds");
        expect((screen.getByLabelText("Class") as HTMLInputElement).disabled).toBe(true);
    });

    it("hides the duration when it is zero", () => {
        render(NemesisDetails, { props: { nemesis: nemesis({ duration: 0 }), resource } });

        expect(screen.queryByLabelText("Duration")).toBeNull();
    });

    it("shows the target node with its private IP and state from the resources", () => {
        render(NemesisDetails, { props: { nemesis: nemesis(), resource } });

        expect(screen.getAllByLabelText("Name").map((input) => (input as HTMLInputElement).value))
            .toEqual(["disrupt_restart_node", "db-node-1"]);
        expect(value("Public IP")).toBe("1.2.3.4");
        expect(value("Private IP")).toBe("10.0.0.5");
        expect(value("State")).toBe("running");
        expect(value("Shards")).toBe("8");
    });

    it("shows not found when the node is missing from the resources", () => {
        render(NemesisDetails, { props: { nemesis: nemesis() } });

        expect(screen.getAllByPlaceholderText("not found")).toHaveLength(2);
        expect(value("Private IP")).toBe("");
        expect(screen.queryByRole("button", { name: "Copy Private IP" })).toBeNull();
    });

    it("copies a field to the clipboard", async () => {
        const writeText = withClipboard();
        render(NemesisDetails, { props: { nemesis: nemesis(), resource } });

        await fireEvent.click(screen.getByRole("button", { name: "Copy Class" }));

        expect(writeText).toHaveBeenCalledWith("DisruptRestartNodeMonkey");
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

        await fireEvent.click(screen.getByRole("button", { name: "Copy" }));

        expect(writeText).toHaveBeenCalledWith("Traceback: boom");
    });

    it("offers no copy buttons when the clipboard is unavailable", () => {
        render(NemesisDetails, { props: { nemesis: nemesis({ status: "failed", stack_trace: "Traceback: boom" }), resource } });

        expect(screen.queryAllByRole("button", { name: /Copy/ })).toHaveLength(0);
    });
});
