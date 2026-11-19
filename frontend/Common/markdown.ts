import { Marked } from "marked";
import { MarkdownUserMention } from "../Discussion/MarkedMentionExtension";
import { sanitizeHtml } from "./safeHtml";

const markdown = new Marked({ gfm: true, breaks: true, async: false });
const markdownWithMentions = new Marked({ gfm: true, breaks: true, async: false, extensions: [MarkdownUserMention] });

export const renderMarkdown = (text: string, { mentions = false }: { mentions?: boolean } = {}): string =>
    sanitizeHtml((mentions ? markdownWithMentions : markdown).parse(text ?? "") as string);
