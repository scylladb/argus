import { Offcanvas } from "bootstrap";

interface OffcanvasOptions {
    onShown?: () => void;
}

export const offcanvas = (node: HTMLElement, options: OffcanvasOptions = {}) => {
    const instance = Offcanvas.getOrCreateInstance(node);
    let current = options;
    const handleShown = () => current.onShown?.();
    node.addEventListener("shown.bs.offcanvas", handleShown);
    return {
        update(next: OffcanvasOptions) {
            current = next;
        },
        destroy() {
            node.removeEventListener("shown.bs.offcanvas", handleShown);
            instance.dispose();
        },
    };
};

export const isDrawer = (node: HTMLElement | undefined): boolean =>
    !!node && getComputedStyle(node).position === "fixed";

export const showDrawer = (node: HTMLElement | undefined): void => {
    if (node) Offcanvas.getOrCreateInstance(node).show();
};

export const hideDrawer = (node: HTMLElement | undefined): void => {
    if (node) Offcanvas.getInstance(node)?.hide();
};
