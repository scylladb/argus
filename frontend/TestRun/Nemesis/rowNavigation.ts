const KEYS = new Set(["ArrowDown", "ArrowUp", "Home", "End"]);

export const rowNavigation = (node: HTMLElement) => {
    const onKeydown = (event: KeyboardEvent) => {
        if (event.target !== node || !KEYS.has(event.key)) {
            return;
        }
        const rows = [...(node.closest(".nemesis-rows")?.querySelectorAll<HTMLElement>(".nemesis-summary") ?? [])];
        const index = rows.indexOf(node);
        const target = {
            ArrowDown: rows[index + 1],
            ArrowUp: rows[index - 1],
            Home: rows[0],
            End: rows[rows.length - 1],
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
