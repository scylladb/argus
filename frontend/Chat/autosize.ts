/** Grows a textarea with its content, up to its CSS max-height. The parameter is
 * the bound text, so a programmatic change (cleared after sending) refits too. */
export const autosize = (textarea: HTMLTextAreaElement, _text?: string) => {
    const fit = () => {
        textarea.style.height = "auto";
        textarea.style.height = `${textarea.scrollHeight + 2}px`;
    };
    textarea.addEventListener("input", fit);
    queueMicrotask(fit);
    return {
        update: () => fit(),
        destroy: () => textarea.removeEventListener("input", fit),
    };
};
