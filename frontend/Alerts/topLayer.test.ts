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

const mounted = () => {
    const home = document.createElement("div");
    const node = document.createElement("div");
    home.append(node);
    document.body.append(home);
    return { home, node };
};

const dialog = () => {
    const element = document.createElement("dialog");
    document.body.append(element);
    return element;
};

afterEach(() => {
    removePopover();
    document.body.replaceChildren();
});

describe("topLayer", () => {
    it("sets no popover without popover support", () => {
        const { node } = mounted();

        const action = topLayer(node, { key: "a" });
        action?.update?.({ key: "b" });
        action?.destroy?.();

        expect(node.hasAttribute("popover")).toBe(false);
    });

    it("moves into the host without popover support", () => {
        const { home, node } = mounted();
        const host = dialog();

        const action = topLayer(node, { key: "a", host });
        expect(node.parentElement).toBe(host);

        action?.update?.({ key: "a", host: null });
        expect(node.parentElement).toBe(home);
    });

    it("shows the node as a manual popover on mount", () => {
        const calls = stubPopover();
        const { node } = mounted();

        topLayer(node, { key: "a" });

        expect(node.getAttribute("popover")).toBe("manual");
        expect(calls).toEqual(["show"]);
    });

    it("raises the node again when the key changes", () => {
        const calls = stubPopover();
        const { node } = mounted();

        const action = topLayer(node, { key: "a" });
        action?.update?.({ key: "b" });

        expect(calls).toEqual(["show", "hide", "show"]);
    });

    it("keeps the node in place when the key repeats", () => {
        const calls = stubPopover();
        const { node } = mounted();

        const action = topLayer(node, { key: "a" });
        action?.update?.({ key: "a" });

        expect(calls).toEqual(["show"]);
    });

    it("moves into the host modal and shows the node there", () => {
        const calls = stubPopover();
        const { node } = mounted();
        const host = dialog();

        const action = topLayer(node, { key: "a" });
        action?.update?.({ key: "a", host });

        expect(node.parentElement).toBe(host);
        expect(calls).toEqual(["show", "show"]);
    });

    it("returns home when the host closes", () => {
        const calls = stubPopover();
        const { home, node } = mounted();
        const host = dialog();

        const action = topLayer(node, { key: "a", host });
        host.remove();
        action?.update?.({ key: "a", host: undefined });

        expect(node.parentElement).toBe(home);
        expect(calls).toEqual(["show", "show"]);
    });

    it("hides the node while it is not shown and shows it again after", () => {
        const calls = stubPopover();
        const { node } = mounted();

        const action = topLayer(node, { key: "a" });
        action?.update?.({ key: "b", shown: false });
        action?.update?.({ key: "c", shown: false });
        action?.update?.({ key: "c", shown: true });

        expect(calls).toEqual(["show", "hide", "show"]);
    });

    it("hides the node on destroy", () => {
        const calls = stubPopover();
        const { home, node } = mounted();

        const action = topLayer(node, { key: "a" });
        action?.destroy?.();

        expect(calls).toEqual(["show", "hide"]);
        expect(node.parentElement).toBe(home);
    });

    it("removes the node from its host on destroy", () => {
        stubPopover();
        const { node } = mounted();
        const host = dialog();

        const action = topLayer(node, { key: "a", host });
        action?.destroy?.();

        expect(node.isConnected).toBe(false);
        expect(host.contains(node)).toBe(false);
    });
});
