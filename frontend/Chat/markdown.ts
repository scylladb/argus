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

/** Model output is untrusted: it can echo run data, comments and issue titles. */
export const renderMarkdown = (text: string): string =>
    DOMPurify.sanitize(chatMarked.parse(text ?? "") as string);
