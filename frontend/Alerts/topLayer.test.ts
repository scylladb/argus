import { describe, it, expect, vi, afterEach } from "vitest";

import { topLayer } from "./topLayer";

const stubPopover = () => {
    const calls: string[] = [];
    Object.defineProperty(HTMLElement.prototype, "showPopover", {
        configurable: true,
        value: vi.fn(() => calls.push("show")),
    });
    Object.defineProperty(HTMLElement.prototype, "hidePopover", {
        configurable: true,
        value: vi.fn(() => calls.push("hide")),
    });
    return calls;
};

const removePopover = () => {
    delete (HTMLElement.prototype as Partial<HTMLElement>).showPopover;
    delete (HTMLElement.prototype as Partial<HTMLElement>).hidePopover;
};

afterEach(() => {
    removePopover();
});

describe("topLayer", () => {
    it("does nothing without popover support", () => {
        const node = document.createElement("div");

        const action = topLayer(node, "a");
        action?.update?.("b");
        action?.destroy?.();

        expect(node.hasAttribute("popover")).toBe(false);
    });

    it("shows the node as a manual popover on mount", () => {
        const calls = stubPopover();
        const node = document.createElement("div");

        topLayer(node, "a");

        expect(node.getAttribute("popover")).toBe("manual");
        expect(calls).toEqual(["show"]);
    });

    it("raises the node again when the key changes", () => {
        const calls = stubPopover();
        const node = document.createElement("div");

        const action = topLayer(node, "a");
        action?.update?.("b");

        expect(calls).toEqual(["show", "hide", "show"]);
    });

    it("keeps the node in place when the key repeats", () => {
        const calls = stubPopover();
        const node = document.createElement("div");

        const action = topLayer(node, "a");
        action?.update?.("a");

        expect(calls).toEqual(["show"]);
    });

    it("hides the node on destroy", () => {
        const calls = stubPopover();
        const node = document.createElement("div");

        const action = topLayer(node, "a");
        action?.destroy?.();

        expect(calls).toEqual(["show", "hide"]);
    });
});
