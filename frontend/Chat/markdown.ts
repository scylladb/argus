import DOMPurify from "dompurify";
import { Marked, type TokenizerAndRendererExtension } from "marked";

/** GFM strikes out text between single tildes, which mangles a line such as
 * "2025.1.0~rc3 and 2025.1.0~rc4". Here a lone tilde stays a tilde; only a
 * double tilde strikes out. */
const singleTilde: TokenizerAndRendererExtension = {
    name: "singleTilde",
    level: "inline",
    start: (src: string) => src.indexOf("~"),
    tokenizer: (src: string) => (/^~(?!~)/.test(src) ? { type: "singleTilde", raw: "~" } : undefined),
    renderer: () => "~",
};

const chatMarked = new Marked({ gfm: true, breaks: true, async: false, extensions: [singleTilde] });

const sameOrigin = (src: string): boolean => {
    try {
        return new URL(src, window.location.href).origin === window.location.origin;
    } catch {
        return false;
    }
};

/** Model output is untrusted: it can echo run data, comments and issue titles. An image from another host
 * would let such text send data out of Argus, so only Argus's own images stay; the others keep their alt text. */
export const renderMarkdown = (text: string): string => {
    const fragment = DOMPurify.sanitize(chatMarked.parse(text ?? "") as string, { RETURN_DOM_FRAGMENT: true });
    for (const image of Array.from(fragment.querySelectorAll("img"))) {
        if (!sameOrigin(image.getAttribute("src") ?? "")) {
            image.replaceWith(document.createTextNode(image.getAttribute("alt") ?? ""));
        }
    }
    const holder = document.createElement("div");
    holder.appendChild(fragment);
    return holder.innerHTML;
};
