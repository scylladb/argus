import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";

import ConfirmDeleteModal from "./ConfirmDeleteModal.svelte";

afterEach(() => {
    cleanup();
});

const renderModal = (props: Record<string, unknown> = {}) => {
    const callbacks = { onConfirm: vi.fn(), onCancel: vi.fn() };
    render(ConfirmDeleteModal, { props: { heading: "Delete test alpha", ...callbacks, ...props } });
    return callbacks;
};

const confirmButton = () => screen.getByRole("button", { name: "Delete" }) as HTMLButtonElement;

describe("ConfirmDeleteModal", () => {
    it("confirms without typing when no name is required", async () => {
        const { onConfirm } = renderModal();

        expect(screen.queryByLabelText(/to confirm/)).toBeNull();
        expect(confirmButton().disabled).toBe(false);
        await fireEvent.click(confirmButton());

        expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it("keeps the button disabled until the typed name matches", async () => {
        const { onConfirm } = renderModal({ confirmName: "alpha-test" });
        const input = screen.getByLabelText(/to confirm/);

        expect(confirmButton().disabled).toBe(true);
        await fireEvent.input(input, { target: { value: "alpha" } });
        expect(confirmButton().disabled).toBe(true);
        await fireEvent.input(input, { target: { value: "alpha-test" } });
        expect(confirmButton().disabled).toBe(false);

        await fireEvent.click(confirmButton());
        expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it("disables both buttons while working", () => {
        renderModal({ working: true });

        expect(confirmButton().disabled).toBe(true);
        expect((screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("cancels from the Cancel button, the close button and Escape", async () => {
        const { onCancel, onConfirm } = renderModal({ confirmName: "alpha-test" });

        await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        await fireEvent.click(screen.getByRole("button", { name: "Close" }));
        await fireEvent.keyDown(window, { key: "Escape" });

        expect(onCancel).toHaveBeenCalledTimes(3);
        expect(onConfirm).not.toHaveBeenCalled();
    });
});
