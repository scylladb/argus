import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, waitFor } from "@testing-library/svelte";
import { tick } from "svelte";
import { alertStore, sendMessage } from "../Stores/AlertStore";
import AlertWidget from "./AlertWidget.svelte";

describe("AlertWidget — sendMessage integration", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        // Reset store to empty between tests
        alertStore.set({});
    });

    afterEach(() => {
        vi.useRealTimers();
        cleanup();
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
});
