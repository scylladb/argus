import { tick } from "svelte";

const FOCUSABLE = "a[href], button, input, select, textarea, [tabindex]:not([tabindex='-1'])";

function isShown(element: HTMLElement, root: HTMLElement): boolean {
    for (let current: HTMLElement | null = element; current && current !== root; current = current.parentElement) {
        if (current.hidden) return false;
        const style = getComputedStyle(current);
        if (style.display === "none" || style.visibility === "hidden") return false;
    }
    return true;
}

function focusableIn(root: HTMLElement): HTMLElement[] {
    return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (element) => !element.matches(":disabled") && isShown(element, root),
    );
}

export function overlayFocus(node: HTMLElement, active = true): { update(next: boolean): void; destroy(): void } {
    let trigger: Element | null = null;
    let open = false;

    const show = () => {
        trigger = document.activeElement;
        open = true;
        tick().then(() => {
            if (open) node.focus({ preventScroll: true });
        });
    };

    const hide = () => {
        open = false;
        if (trigger instanceof HTMLElement && trigger.isConnected) {
            trigger.focus({ preventScroll: true });
        }
        trigger = null;
    };

    const wrapTab = (event: KeyboardEvent) => {
        if (event.key !== "Tab") return;
        const controls = focusableIn(node);
        if (controls.length === 0) return;
        const first = controls[0];
        const last = controls[controls.length - 1];
        const current = document.activeElement;
        if (event.shiftKey && (current === first || current === node)) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && current === last) {
            event.preventDefault();
            first.focus();
        }
    };

    node.addEventListener("keydown", wrapTab);
    if (active) show();

    return {
        update(next: boolean) {
            if (next && !open) show();
            else if (!next && open) hide();
        },
        destroy() {
            node.removeEventListener("keydown", wrapTab);
            if (open) hide();
        },
    };
}
