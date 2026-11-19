import type { ActionReturn } from "svelte/action";

export interface TopLayerParams {
    key: unknown;
    host?: HTMLElement | null;
    shown?: boolean;
}

export function topLayer(node: HTMLElement, params: TopLayerParams): ActionReturn<TopLayerParams> {
    const home = node.parentElement;
    const popover = "showPopover" in HTMLElement.prototype;
    let current = params;
    let open = false;

    const place = (next: TopLayerParams, raise: boolean) => {
        const target = next.host ?? home;
        if (target && node.parentElement !== target) {
            target.append(node);
            open = false;
        }
        if (!popover) return;
        if (next.shown === false) {
            if (open) node.hidePopover();
            open = false;
        } else if (raise || !open) {
            if (open) node.hidePopover();
            node.showPopover();
            open = true;
        }
    };

    if (popover) node.setAttribute("popover", "manual");
    place(params, true);

    return {
        update(next) {
            const raise = next.key !== current.key;
            current = next;
            place(next, raise);
        },
        destroy() {
            if (open) node.hidePopover();
            if (node.parentElement !== home) node.remove();
        },
    };
}
