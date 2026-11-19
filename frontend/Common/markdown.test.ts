import { describe, expect, it, vi } from "vitest";
import { renderMarkdown } from "./markdown";

vi.mock("../argus", () => ({ applicationCurrentUser: { username: "admin" } }));

const parse = (html: string): HTMLElement => {
    const holder = document.createElement("div");
    holder.innerHTML = html;
    return holder;
};

describe("renderMarkdown", () => {
    it("drops a javascript: link", () => {
        const html = renderMarkdown("[x](javascript:alert(1))");

        expect(parse(html).querySelector("a")?.hasAttribute("href")).toBe(false);
        expect(html).not.toContain("javascript:");
    });

    it("drops a javascript: link written with an entity", () => {
        const html = renderMarkdown("[x](javascript&#58;alert(1))");

        expect(parse(html).querySelector("a")?.hasAttribute("href")).toBe(false);
        expect(html).not.toContain("javascript");
    });

    it("strips an event handler from raw HTML", () => {
        const image = parse(renderMarkdown('<img src="x" onerror="alert(1)">')).querySelector("img");

        expect(image).not.toBeNull();
        expect(image?.hasAttribute("onerror")).toBe(false);
    });

    it("keeps ordinary markdown", () => {
        const html = renderMarkdown([
            "**b** `c` [ok](https://example.com)",
            "```js\nconst a = 1;\n```",
            "| a | b |\n|---|---|\n| 1 | 2 |",
            "- [x] done",
        ].join("\n\n"));
        const node = parse(html);

        expect(node.querySelector("strong")?.textContent).toBe("b");
        expect(node.querySelector("p > code")?.textContent).toBe("c");
        expect(node.querySelector("pre > code.language-js")?.textContent).toBe("const a = 1;\n");
        expect(node.querySelector("a")?.getAttribute("href")).toBe("https://example.com");
        expect(node.querySelectorAll("table td")).toHaveLength(2);
        const checkbox = node.querySelector<HTMLInputElement>("li input[type=checkbox]");
        expect(checkbox?.checked).toBe(true);
        expect(checkbox?.disabled).toBe(true);
    });

    it("renders a mention only when asked", () => {
        expect(parse(renderMarkdown("hi @admin", { mentions: true })).querySelector("span.user-mention")?.textContent)
            .toBe("@admin");
        expect(parse(renderMarkdown("hi @admin")).querySelector("span.user-mention")).toBeNull();
        expect(renderMarkdown("hi @admin")).toContain("hi @admin");
    });
});
