import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { tick } from "svelte";
import { overlayFocus } from "./overlayFocus";

let trigger: HTMLButtonElement;
let overlay: HTMLDivElement;

beforeEach(() => {
    trigger = document.createElement("button");
    overlay = document.createElement("div");
    overlay.tabIndex = -1;
    document.body.append(trigger, overlay);
    trigger.focus();
});

afterEach(() => {
    document.body.replaceChildren();
});

describe("overlayFocus", () => {
    it("moves the focus after the pending DOM update, not before", async () => {
        overlayFocus(overlay);

        expect(document.activeElement).toBe(trigger);
        await tick();
        expect(document.activeElement).toBe(overlay);
    });

    it("moves the focus to an overlay that mounts open", async () => {
        overlayFocus(overlay);
        await tick();

        expect(document.activeElement).toBe(overlay);
    });

    it("leaves the focus alone while the overlay is closed", async () => {
        overlayFocus(overlay, false);
        await tick();

        expect(document.activeElement).toBe(trigger);
    });

    it("moves the focus in on open and back to the trigger on close", async () => {
        const action = overlayFocus(overlay, false);

        action.update(true);
        await tick();
        expect(document.activeElement).toBe(overlay);

        action.update(false);
        expect(document.activeElement).toBe(trigger);
    });

    it("returns the focus to the trigger when an open overlay unmounts", async () => {
        const action = overlayFocus(overlay);
        await tick();

        action.destroy();

        expect(document.activeElement).toBe(trigger);
    });

    it("keeps the focus where it is when the trigger is gone", async () => {
        const action = overlayFocus(overlay);
        await tick();
        trigger.remove();
        const other = document.createElement("button");
        document.body.append(other);
        other.focus();

        action.destroy();

        expect(document.activeElement).toBe(other);
    });
});

describe("overlayFocus Tab wrap", () => {
    let first: HTMLButtonElement;
    let middle: HTMLInputElement;
    let last: HTMLButtonElement;

    const press = (target: HTMLElement, shiftKey = false) => {
        const event = new KeyboardEvent("keydown", { key: "Tab", shiftKey, bubbles: true, cancelable: true });
        target.dispatchEvent(event);
        return event;
    };

    beforeEach(() => {
        first = document.createElement("button");
        middle = document.createElement("input");
        last = document.createElement("button");
        const disabled = document.createElement("button");
        disabled.disabled = true;
        const hidden = document.createElement("button");
        hidden.hidden = true;
        const undisplayed = document.createElement("div");
        undisplayed.style.display = "none";
        undisplayed.append(document.createElement("button"));
        overlay.append(first, middle, last, disabled, hidden, undisplayed);
    });

    it("moves Tab from the last control to the first", () => {
        overlayFocus(overlay);
        last.focus();

        const event = press(last);

        expect(event.defaultPrevented).toBe(true);
        expect(document.activeElement).toBe(first);
    });

    it("moves Shift+Tab from the first control to the last", () => {
        overlayFocus(overlay);
        first.focus();

        const event = press(first, true);

        expect(event.defaultPrevented).toBe(true);
        expect(document.activeElement).toBe(last);
    });

    it("moves Shift+Tab from the overlay itself to the last control", () => {
        overlayFocus(overlay);
        overlay.focus();

        press(overlay, true);

        expect(document.activeElement).toBe(last);
    });

    it("leaves Tab between inner controls to the browser", () => {
        overlayFocus(overlay);
        middle.focus();

        expect(press(middle).defaultPrevented).toBe(false);
        expect(press(middle, true).defaultPrevented).toBe(false);
    });

    it("stops wrapping once destroyed", () => {
        const action = overlayFocus(overlay);
        action.destroy();
        last.focus();

        expect(press(last).defaultPrevented).toBe(false);
    });
});
