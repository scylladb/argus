export function tooltipAnchor(
    canvas: HTMLCanvasElement,
    caretX: number,
    caretY: number,
): { host: HTMLElement; left: number; top: number } {
    const rect = canvas.getBoundingClientRect();
    const dialog = canvas.closest("dialog");
    if (!dialog) {
        return {
            host: document.body,
            left: rect.left + window.scrollX + caretX,
            top: rect.top + window.scrollY + caretY,
        };
    }
    const hostRect = dialog.getBoundingClientRect();
    return {
        host: dialog,
        left: rect.left - hostRect.left + dialog.scrollLeft + caretX,
        top: rect.top - hostRect.top + dialog.scrollTop + caretY,
    };
}
