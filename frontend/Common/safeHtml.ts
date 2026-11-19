import DOMPurify from "dompurify";

const purifier = DOMPurify(window);

purifier.addHook("afterSanitizeAttributes", (node) => {
    if (node instanceof Element && node.hasAttribute("target")) {
        node.setAttribute("rel", "noopener noreferrer");
    }
});

export const sanitizeHtml = (html: string | null | undefined): string =>
    purifier.sanitize(html ?? "", { ADD_ATTR: ["target"] });
