const KEYS = new Set(["ArrowDown", "ArrowUp", "Home", "End"]);

export const rowNavigation = (node: HTMLElement) => {
    const onKeydown = (event: KeyboardEvent) => {
        if (event.target !== node || !KEYS.has(event.key)) {
            return;
        }
        const toggles = [...(node.closest(".nemesis-rows")?.querySelectorAll<HTMLElement>(".nemesis-toggle") ?? [])];
        const index = toggles.indexOf(node);
        const target = {
            ArrowDown: toggles[index + 1],
            ArrowUp: toggles[index - 1],
            Home: toggles[0],
            End: toggles[toggles.length - 1],
        }[event.key];
        if (target) {
            event.preventDefault();
            target.focus();
        }
    };
    node.addEventListener("keydown", onKeydown);
    return {
        destroy() {
            node.removeEventListener("keydown", onKeydown);
        },
    };
};
