import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/svelte";
import { tick } from "svelte";
import { alertStore, sendMessage } from "../Stores/AlertStore";
import { openModals } from "../Stores/ModalStore";
import AlertWidget from "./AlertWidget.svelte";

describe("AlertWidget — sendMessage integration", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        // Reset store to empty between tests
        alertStore.set({});
        openModals.set([]);
    });

    afterEach(() => {
        vi.useRealTimers();
        cleanup();
        document.body.replaceChildren();
    });

    it("renders an error message after sendMessage is called", async () => {
        render(AlertWidget);
        await tick();

        sendMessage("error", "Something went wrong", "TestSource");
        await tick();
        await tick();

        expect(screen.getByText("Something went wrong")).toBeTruthy();
        expect(screen.getByText("An error occurred.")).toBeTruthy();
        expect(screen.getByText(/TestSource/)).toBeTruthy();
    });

    it("renders a success message", async () => {
        render(AlertWidget);
        await tick();

        sendMessage("success", "Operation completed");
        await tick();
        await tick();

        expect(screen.getByText("Operation completed")).toBeTruthy();
        expect(screen.getByText("Success.")).toBeTruthy();
    });

    it("renders an info message", async () => {
        render(AlertWidget);
        await tick();

        sendMessage("info", "FYI something happened");
        await tick();
        await tick();

        expect(screen.getByText("FYI something happened")).toBeTruthy();
        expect(screen.getByText("Info")).toBeTruthy();
    });

    it("renders multiple messages simultaneously", async () => {
        render(AlertWidget);
        await tick();

        sendMessage("error", "Error one");
        sendMessage("success", "Success two");
        sendMessage("info", "Info three");
        await tick();
        await tick();

        expect(screen.getByText("Error one")).toBeTruthy();
        expect(screen.getByText("Success two")).toBeTruthy();
        expect(screen.getByText("Info three")).toBeTruthy();
    });

    it("auto-dismisses a message after 8 seconds", async () => {
        render(AlertWidget);
        await tick();

        sendMessage("info", "Ephemeral message");
        await tick();
        await tick();

        expect(screen.getByText("Ephemeral message")).toBeTruthy();

        vi.advanceTimersByTime(8000);
        await tick();
        await tick();

        expect(screen.queryByText("Ephemeral message")).toBeNull();
    });

    it("dismisses a message when the close button is clicked", async () => {
        render(AlertWidget);
        await tick();

        sendMessage("error", "Dismissable error");
        await tick();
        await tick();

        const closeBtn = screen.getAllByRole("button", { name: "Dismiss" })[0];
        closeBtn.click();
        await tick();
        await tick();

        expect(screen.queryByText("Dismissable error")).toBeNull();
    });

    it("renders flash messages passed as props", async () => {
        render(AlertWidget, {
            props: {
                flashes: [
                    ["error", "Flash error"],
                    ["success", "Flash success"],
                ],
            },
        });
        await tick();
        await tick();

        expect(screen.getByText("Flash error")).toBeTruthy();
        expect(screen.getByText("Flash success")).toBeTruthy();
    });

    it("opens the error console as a modal dialog and closes it with Clear all", async () => {
        render(AlertWidget);
        await tick();
        sendMessage("error", "Saved error");
        await tick();
        await tick();
        screen.getByRole("button", { name: "Dismiss" }).click();
        await tick();

        screen.getByRole("button", { name: "Show errors" }).click();
        await tick();
        await tick();

        const errorConsole = screen.getByRole("dialog", { name: "Error console" }) as HTMLDialogElement;
        expect(errorConsole.open).toBe(true);
        expect(errorConsole.textContent).toContain("Saved error");

        screen.getByRole("button", { name: "Clear all" }).click();
        await tick();
        await tick();

        expect(screen.queryByRole("dialog", { name: "Error console" })).toBeNull();
        expect(screen.queryByRole("button", { name: "Show errors" })).toBeNull();
    });

    it("closes the error console when its dialog closes", async () => {
        render(AlertWidget);
        await tick();
        sendMessage("error", "Saved error");
        await tick();
        await tick();
        screen.getByRole("button", { name: "Dismiss" }).click();
        await tick();
        screen.getByRole("button", { name: "Show errors" }).click();
        await tick();
        await tick();

        (screen.getByRole("dialog", { name: "Error console" }) as HTMLDialogElement).close();
        await tick();
        await tick();

        expect(screen.queryByRole("dialog", { name: "Error console" })).toBeNull();
        expect(screen.getByRole("button", { name: "Show errors" })).toBeTruthy();
    });

    it("moves the toast stack into the open modal and back when it closes", async () => {
        const { container } = render(AlertWidget);
        await tick();
        sendMessage("error", "Failed save");
        await tick();
        await tick();
        const stack = document.getElementById("alertWidget") as HTMLElement;
        const home = stack.parentElement;
        const modal = document.createElement("dialog");
        document.body.append(modal);

        openModals.set([modal]);
        await tick();

        expect(stack.parentElement).toBe(modal);
        expect(modal.textContent).toContain("Failed save");

        openModals.set([]);
        await tick();

        expect(stack.parentElement).toBe(home);
        expect(container.contains(stack)).toBe(true);
    });
});
