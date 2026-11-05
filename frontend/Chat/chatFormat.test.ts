import { describe, expect, it } from "vitest";
import { preview } from "./chatFormat";

describe("preview", () => {
    it("flattens markdown and tables into one readable line", () => {
        const text = "On **rc4**, 16 tests failed:\n\n| Count | Test |\n| :--- | :--- |\n| 1 | `upgrade-test` |";
        expect(preview(text)).toBe("On rc4, 16 tests failed: Count · Test 1 · upgrade-test");
    });

    it("keeps the underscores of names and drops emphasis", () => {
        expect(preview("Call _get_summary_ or get_run_events for **rc4**")).toBe(
            "Call get_summary or get_run_events for rc4");
    });

    it("cuts long text", () => {
        expect(preview("word ".repeat(100), 20)).toBe("word word word word…");
    });
});
