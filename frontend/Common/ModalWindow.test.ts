import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import { createRawSnippet } from "svelte";

import ModalWindow from "./ModalWindow.svelte";

const snippet = (html: string) => createRawSnippet(() => ({ render: () => html }));

const renderModal = (props: Record<string, unknown> = {}) => {
    const onClose = vi.fn();
    const result = render(ModalWindow, {
        props: {
            title: snippet("<span>Edit the run</span>"),
            body: snippet(`<div><input aria-label="Run name" /><p>Body text</p></div>`),
            ...props,
        },
        events: { modalClose: onClose },
    });
    const dialog = screen.getByRole("dialog") as HTMLDialogElement;
    return { ...result, dialog, onClose };
};

const outsideButton = (name: string) => {
    const button = document.createElement("button");
    button.textContent = name;
    document.body.append(button);
    return button;
};

afterEach(() => {
    cleanup();
    document.body.replaceChildren();
});

describe("ModalWindow", () => {
    it("opens a dialog named by its title", () => {
        const { dialog } = renderModal();

        expect(screen.getByRole("dialog", { name: "Edit the run" })).toBe(dialog);
        expect(dialog.open).toBe(true);
        expect(dialog.contains(screen.getByText("Body text"))).toBe(true);
    });

    it("has no accessible name without a title", () => {
        const { dialog } = renderModal({ title: undefined });

        expect(dialog.hasAttribute("aria-labelledby")).toBe(false);
    });

    it("dispatches modalClose from the close button", async () => {
        const { onClose } = renderModal();

        await fireEvent.click(screen.getByRole("button", { name: "Close" }));

        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("dispatches modalClose when the dialog closes", () => {
        const { dialog, onClose } = renderModal();

        dialog.close();

        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("ignores an Escape keydown on the window", async () => {
        const { onClose } = renderModal();

        await fireEvent.keyDown(window, { key: "Escape" });

        expect(onClose).not.toHaveBeenCalled();
    });

    it("returns the focus to the opener on unmount", () => {
        const opener = outsideButton("Open");
        opener.focus();
        const { unmount } = renderModal();
        screen.getByRole("button", { name: "Close" }).focus();

        unmount();

        expect(document.activeElement).toBe(opener);
    });

    it("leaves the focus alone when it moved outside", () => {
        const opener = outsideButton("Open");
        opener.focus();
        const { unmount } = renderModal();
        const other = outsideButton("Other");
        other.focus();

        unmount();

        expect(document.activeElement).toBe(other);
    });

    it("does not throw when the opener is gone", () => {
        const opener = outsideButton("Open");
        opener.focus();
        const { unmount } = renderModal();
        screen.getByRole("button", { name: "Close" }).focus();
        opener.remove();

        expect(() => unmount()).not.toThrow();
        expect(document.activeElement).toBe(document.body);
    });

    it("closes on a click outside the box", async () => {
        const { dialog, onClose } = renderModal();

        await fireEvent.pointerDown(dialog);
        await fireEvent.pointerUp(dialog);
        await fireEvent.click(dialog);

        expect(dialog.open).toBe(false);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("closes on a click on the frame around the box", async () => {
        const { dialog, onClose } = renderModal();
        const frame = dialog.firstElementChild as HTMLElement;

        await fireEvent.pointerDown(frame);
        await fireEvent.pointerUp(frame);
        await fireEvent.click(frame);

        expect(dialog.open).toBe(false);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("stays open on a click inside the box", async () => {
        const { dialog, onClose } = renderModal();
        const title = screen.getByText("Edit the run");

        await fireEvent.pointerDown(title);
        await fireEvent.pointerUp(title);
        await fireEvent.click(title);

        expect(dialog.open).toBe(true);
        expect(onClose).not.toHaveBeenCalled();
    });

    it("stays open after a drag from the box to the outside", async () => {
        const { dialog, onClose } = renderModal();

        await fireEvent.pointerDown(screen.getByRole("textbox", { name: "Run name" }));
        await fireEvent.pointerUp(dialog);
        await fireEvent.click(dialog);

        expect(dialog.open).toBe(true);
        expect(onClose).not.toHaveBeenCalled();
    });

    it("stays open after a drag from the outside into the box", async () => {
        const { dialog, onClose } = renderModal();
        const frame = dialog.firstElementChild as HTMLElement;

        await fireEvent.pointerDown(frame);
        await fireEvent.pointerUp(screen.getByRole("textbox", { name: "Run name" }));
        await fireEvent.click(frame);

        expect(dialog.open).toBe(true);
        expect(onClose).not.toHaveBeenCalled();
    });
});
