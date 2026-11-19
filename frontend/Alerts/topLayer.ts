import type { ActionReturn } from "svelte/action";

export function topLayer(node: HTMLElement, key: unknown): ActionReturn<unknown> {
    if (!("showPopover" in HTMLElement.prototype)) return {};

    let current = key;
    node.setAttribute("popover", "manual");
    node.showPopover();

    return {
        update(next) {
            if (next === current) return;
            current = next;
            node.hidePopover();
            node.showPopover();
        },
        destroy() {
            node.hidePopover();
        },
    };
}
