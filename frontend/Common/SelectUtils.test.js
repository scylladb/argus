import { describe, it, expect } from "vitest";
import { filterUser } from "./SelectUtils.js";

describe("filterUser", () => {
    it("matches when label contains the filter text (case-insensitive)", () => {
        expect(filterUser("JohnDoe", "", null)).toBe(true);
        expect(filterUser("JohnDoe", "john", null)).toBe(true);
        // filterText is lowercased internally, so uppercase input still matches
        expect(filterUser("JohnDoe", "JOHN", null)).toBe(true);
    });

    it("matches against the user full_name as well", () => {
        const user = { full_name: "Jane Smith" };
        expect(filterUser("jsmith", "jane", user)).toBe(true);
        expect(filterUser("jsmith", "smith", user)).toBe(true);
    });

    it("handles null label gracefully", () => {
        const user = { full_name: "Alice" };
        expect(filterUser(null, "alice", user)).toBe(true);
    });

    it("handles null user gracefully", () => {
        expect(filterUser("bob", "bob", null)).toBe(true);
    });

    it("handles unicode characters in names", () => {
        const user = { full_name: "Łukasz" };
        // The url-slug dictionary maps Ł -> L
        expect(filterUser("", "l", user)).toBe(true);
    });

    it("returns false when filter text does not match", () => {
        const user = { full_name: "Charlie" };
        expect(filterUser("charlie_user", "zzz", user)).toBe(false);
    });
});
