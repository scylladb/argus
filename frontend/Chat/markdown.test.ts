import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
    it("keeps the tilde of release candidates", () => {
        const html = renderMarkdown("2025.1.0~rc3 failed 25 tests and 2025.1.0~rc4 failed 16");

        expect(html).not.toContain("<del>");
        expect(html).toContain("2025.1.0~rc3 failed 25 tests and 2025.1.0~rc4 failed 16");
    });

    it("still strikes through with a double tilde", () => {
        expect(renderMarkdown("~~gone~~ and ~rc1")).toContain("<del>gone</del> and ~rc1");
    });

    it("leaves code alone", () => {
        expect(renderMarkdown("`2025.1.0~rc3` and ~~old~~")).toContain("<code>2025.1.0~rc3</code>");
    });
});
